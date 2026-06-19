from urllib.request import urlopen, build_opener, ProxyHandler, ProxyBasicAuthHandler, HTTPPasswordMgrWithDefaultRealm
import urllib.parse
from urllib.error import URLError

from core.ports import HtmlFetcherPort
from adapters.botting.l4_transport.proxy_config import ProxyConfig

class HttpClient(HtmlFetcherPort):
    """OSI Layer 4 (Transport): Physical network communication and basic HTTP."""

    def __init__(self, proxy_config: ProxyConfig = None):
        self._proxy_config = proxy_config

    def fetch(self, url: str) -> str:
        """Fetch raw HTML/text from a URL."""
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
                    return response.read().decode("utf-8")
            else:
                with urlopen(url) as response:
                    return response.read().decode("utf-8")
        except URLError as e:
            raise RuntimeError(f"Network error fetching {url}: {e}")

