import io
import urllib.request
import urllib.parse
from urllib.request import build_opener, ProxyHandler, ProxyBasicAuthHandler, HTTPPasswordMgrWithDefaultRealm
from urllib.error import URLError
from typing import Union, Optional
from pypdf import PdfReader
from adapters.botting.l4_transport.proxy_config import ProxyConfig

class PdfParser:
    """Helper to download and extract text content from PDF documents."""

    def __init__(self, proxy_config: Optional[ProxyConfig] = None):
        self._proxy_config = proxy_config

    def download_pdf(self, url: str) -> bytes:
        """Download a PDF file from a URL, respecting proxy configuration."""
        try:
            active_proxy = self._proxy_config.get_active_proxy_url() if self._proxy_config else None
            
            if active_proxy:
                parsed = urllib.parse.urlparse(active_proxy)
                proxy_server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}" if parsed.port else f"{parsed.scheme}://{parsed.hostname}"
                
                handlers = []
                proxy_handler = ProxyHandler({'http': proxy_server, 'https': proxy_server})
                handlers.append(proxy_handler)
                
                if parsed.username and parsed.password:
                    password_mgr = HTTPPasswordMgrWithDefaultRealm()
                    password_mgr.add_password(None, proxy_server, parsed.username, parsed.password)
                    auth_handler = ProxyBasicAuthHandler(password_mgr)
                    handlers.append(auth_handler)
                    
                opener = build_opener(*handlers)
                opener.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")]
                with opener.open(url) as response:
                    return response.read()
            else:
                req = urllib.request.Request(
                    url, 
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                with urllib.request.urlopen(req) as response:
                    return response.read()
        except URLError as e:
            raise RuntimeError(f"Network error downloading PDF from {url}: {e}")

    def extract_text(self, pdf_bytes: bytes) -> str:
        """Extract text from a bytes stream of a PDF file using pypdf."""
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            text_parts = []
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text_parts.append(extracted)
            return "\n".join(text_parts)
        except Exception as e:
            raise RuntimeError(f"Failed to parse PDF bytes: {e}")

    def parse(self, target: Union[str, bytes]) -> str:
        """Parse a PDF from a URL (str) or a byte stream (bytes)."""
        if isinstance(target, bytes):
            return self.extract_text(target)
        elif isinstance(target, str):
            pdf_bytes = self.download_pdf(target)
            return self.extract_text(pdf_bytes)
        else:
            raise TypeError("Target must be either a URL string or bytes stream")
