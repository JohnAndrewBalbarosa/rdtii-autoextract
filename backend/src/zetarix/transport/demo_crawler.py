import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import sys
import os
import socket
import json

# Add backend to path
sys.path.append("C:/Users/Drew/Desktop/rdtii-autoextract/backend/src")

from zetarix.transport.proxy_config import ProxyConfig
from zetarix.transport.advanced_crawler import AdvancedCrawler

# Minimal valid PDF file containing the text "Hello PDF Content"
MINI_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj\n"
    b"4 0 obj\n<< /Length 51 >>\nstream\nBT\n/F1 12 Tf\n70 700 Td\n(Hello PDF Content) Tj\nET\nendstream\nendobj\n"
    b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    b"xref\n"
    b"0 6\n"
    b"0000000000 65535 f\n"
    b"0000000009 00000 n\n"
    b"0000000056 00000 n\n"
    b"0000000111 00000 n\n"
    b"0000000223 00000 n\n"
    b"0000000323 00000 n\n"
    b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
    b"startxref\n"
    b"416\n"
    b"%%EOF\n"
)

class MockWebServer(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        
        if parsed_url.path == "/" or parsed_url.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            
            html = """
            <!DOCTYPE html>
            <html>
              <head>
                <title>Test Page</title>
                <style>body { font-family: sans-serif; }</style>
              </head>
              <body>
                <header>
                  <nav><a href="#home">Home</a> | <a href="#about">About</a></nav>
                </header>
                
                <main>
                  <h1>Scraping Sandbox</h1>
                  <p>Welcome to the scraping test page.</p>
                  
                  <!-- Link directly in body -->
                  <a href="/files/document1.pdf">Download Document 1 PDF</a>
                </main>
                
                <footer>
                  <p>Copyright 2026 Sandbox Corp.</p>
                </footer>
                
                <!-- Inline JavaScript script containing a PDF link -->
                <script>
                  var secretDoc = "http://127.0.0.1:{{PORT}}/files/document2.pdf";
                  console.log("Loading " + secretDoc);
                </script>
                
                <!-- External JS script link -->
                <script src="/js/app.js"></script>
              </body>
            </html>
            """
            # Replace placeholder with server port
            port = self.server.server_address[1]
            html = html.replace("{{PORT}}", str(port))
            self.wfile.write(html.encode("utf-8"))
            
        elif parsed_url.path == "/js/app.js":
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.end_headers()
            
            js = """
            // JavaScript file containing an embedded PDF link
            const documentUrl = "http://127.0.0.1:{{PORT}}/files/document3.pdf";
            function loadPdf() {
                fetch(documentUrl);
            }
            """
            port = self.server.server_address[1]
            js = js.replace("{{PORT}}", str(port))
            self.wfile.write(js.encode("utf-8"))
            
        elif parsed_url.path.startswith("/files/document") and parsed_url.path.endswith(".pdf"):
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.end_headers()
            self.wfile.write(MINI_PDF_BYTES)
            
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format, *args):
        # Suppress logging to keep demo output neat
        pass

def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def run_demo():
    port = get_free_port()
    server = HTTPServer(("127.0.0.1", port), MockWebServer)
    
    # Start server in daemon thread
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    
    print("=" * 80)
    print(" ADVANCED CRAWLER & PARSER DEMO")
    print("=" * 80)
    print(f"1. Started mock target server on http://127.0.0.1:{port}")
    print("2. Running AdvancedCrawler...")
    
    # Initialize crawler (using simulated proxy rotation settings or direct)
    crawler = AdvancedCrawler()
    
    # Target URL
    target_url = f"http://127.0.0.1:{port}/"
    result = crawler.crawl(target_url)
    
    print("\n[RESULT] Cleaned HTML Content (Excluding Headers, Footers, Navs, Scripts, Styles):")
    print("-" * 80)
    print(result["cleaned_html"].strip())
    print("-" * 80)
    
    print("\n[RESULT] Discovered PDF Links (Scanned from HTML, Inline Scripts, and External JS):")
    for link in result["pdf_links"]:
        # Extract relative name
        name = link.split("/")[-1]
        print(f"  +-- Found Link: {link} ({name})")
        
    print("\n[RESULT] Extracted PDF Content (Parsed via pypdf):")
    for link, content in result["pdf_contents"].items():
        name = link.split("/")[-1]
        print(f"  +-- File: {name}")
        print(f"      +-- Extracted Text: {content.strip()}")
        
    print("=" * 80)
    
    # Shutdown server
    server.shutdown()
    server.server_close()

if __name__ == "__main__":
    run_demo()
