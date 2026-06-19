import pytest
from unittest.mock import MagicMock, patch
from adapters.botting.l4_transport.proxy_config import ProxyConfig
from adapters.botting.l4_transport.advanced_crawler import AdvancedCrawler
from adapters.botting.l4_transport.pdf_parser import PdfParser

def test_fallback_on_fetch_error():
    # Verify: BS4 fallback on fetch error (i.e. fallback to HttpClient when PlaywrightClient fails)
    crawler = AdvancedCrawler()
    
    # Mock PlaywrightClient.fetch to fail
    crawler.playwright_client.fetch = MagicMock(side_effect=RuntimeError("Playwright failed"))
    # Mock HttpClient.fetch to succeed
    crawler.http_client.fetch = MagicMock(return_value="<html><body>Static Content</body></html>")
    
    html = crawler.fetch_page("http://example.com")
    
    assert html == "<html><body>Static Content</body></html>"
    crawler.playwright_client.fetch.assert_called_once_with("http://example.com")
    crawler.http_client.fetch.assert_called_once_with("http://example.com")

def test_cleaning_of_html():
    # Verify: Cleaning of HTML headers/footers, navs, styles, templates
    crawler = AdvancedCrawler()
    
    dirty_html = """
    <html>
      <head>
        <style>body { color: red; }</style>
      </head>
      <body>
        <header>
          <h1>Site Header</h1>
          <nav><a href="/home">Home</a></nav>
        </header>
        <main>
          <h2>Main Content Heading</h2>
          <p>This is the important main body content.</p>
        </main>
        <footer>
          <p>Copyright 2026</p>
        </footer>
        <template>
          <div>Template item</div>
        </template>
        <noscript>No JS support</noscript>
        <script>console.log("Ignore me");</script>
      </body>
    </html>
    """
    
    cleaned = crawler.clean_html(dirty_html)
    
    # Assert excluded components are gone
    assert "Site Header" not in cleaned
    assert "Home" not in cleaned
    assert "Copyright" not in cleaned
    assert "Template item" not in cleaned
    assert "Ignore me" not in cleaned
    assert "No JS support" not in cleaned
    assert "body { color: red; }" not in cleaned
    
    # Assert main content remains
    assert "Main Content Heading" in cleaned
    assert "important main body content" in cleaned

def test_extraction_of_pdf_links_and_external_js():
    # Verify: Extraction of PDF links from HTML and external JS files via regex
    crawler = AdvancedCrawler()
    
    html_content = """
    <html>
      <body>
        <p>Here is a PDF link: <a href="https://example.com/files/report.pdf">Download</a></p>
        <p>Another PDF link in text: http://example.org/documents/law_v1.pdf</p>
        
        <script>
          // Inline script containing a PDF link
          var docUrl = 'https://example.com/assets/secret_inline.pdf';
        </script>
        
        <!-- External JS files -->
        <script src="/js/analytics.js"></script>
        <script src="https://external.com/bundle.js"></script>
      </body>
    </html>
    """
    
    # Mock playwright fetch to return the html_content
    crawler.playwright_client.fetch = MagicMock(return_value=html_content)
    
    # Mock http fetch for external JS files.
    # When fetching external.com bundle or local analytics.js, we return JS code with PDF links.
    def mock_http_fetch(url):
        if "/js/analytics.js" in url:
            return "const pdf1 = 'https://example.com/js_local.pdf';"
        elif "external.com/bundle.js" in url:
            return "var myPdf = \"https://example.com/js_external.pdf\";"
        elif "report.pdf" in url or "law_v1.pdf" in url or "secret_inline.pdf" in url or "js_local.pdf" in url or "js_external.pdf" in url:
            return b"PDF data dummy"
        return ""
        
    crawler.http_client.fetch = MagicMock(side_effect=mock_http_fetch)
    
    # Mock PdfParser's parse method so we don't try to parse dummy pdf data using real pypdf in this test
    crawler.pdf_parser.parse = MagicMock(return_value="Extracted text content of PDF")
    
    result = crawler.crawl("https://example.com/home")
    
    # Check that links are successfully found
    pdf_links = result["pdf_links"]
    assert "https://example.com/files/report.pdf" in pdf_links
    assert "http://example.org/documents/law_v1.pdf" in pdf_links
    assert "https://example.com/assets/secret_inline.pdf" in pdf_links
    assert "https://example.com/js_local.pdf" in pdf_links
    assert "https://example.com/js_external.pdf" in pdf_links
    
    # Check that pdf parsing was triggered for all discovered PDFs
    assert len(result["pdf_contents"]) == 5
    for link in pdf_links:
        assert result["pdf_contents"][link] == "Extracted text content of PDF"

def test_download_and_parse_pdf():
    # Verify: Downloading and parsing of PDF content
    pdf_parser = PdfParser()
    
    mock_pdf_bytes = b"%PDF-1.4 mock data"
    
    # Mock download_pdf
    pdf_parser.download_pdf = MagicMock(return_value=mock_pdf_bytes)
    
    # Patch pypdf PdfReader
    with patch("adapters.botting.l4_transport.pdf_parser.PdfReader") as mock_pdf_reader:
        mock_reader_inst = MagicMock()
        mock_page_1 = MagicMock()
        mock_page_1.extract_text.return_value = "Page 1 Content"
        mock_page_2 = MagicMock()
        mock_page_2.extract_text.return_value = "Page 2 Content"
        
        mock_reader_inst.pages = [mock_page_1, mock_page_2]
        mock_pdf_reader.return_value = mock_reader_inst
        
        # Test parsing with url
        text_from_url = pdf_parser.parse("https://example.com/doc.pdf")
        assert "Page 1 Content" in text_from_url
        assert "Page 2 Content" in text_from_url
        pdf_parser.download_pdf.assert_called_once_with("https://example.com/doc.pdf")
        mock_pdf_reader.assert_called_once()
        
        # Test parsing with bytes
        mock_pdf_reader.reset_mock()
        text_from_bytes = pdf_parser.parse(mock_pdf_bytes)
        assert "Page 1 Content" in text_from_bytes
        assert "Page 2 Content" in text_from_bytes
        mock_pdf_reader.assert_called_once()
