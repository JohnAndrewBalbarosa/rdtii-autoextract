import urllib.parse
import uuid
import threading
import time
import re
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
import urllib.request

class FreeProxyManager:
    """Fetches, caches, and rotates public proxies from free-proxy-list.net."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super(FreeProxyManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
            
    def __init__(self, cache_ttl_seconds: int = 600):
        if self._initialized:
            return
        self.cache_ttl = cache_ttl_seconds
        self.proxies: List[str] = []
        self.last_fetched = 0.0
        self.current_index = 0
        self.lock = threading.Lock()
        self._initialized = True
        
    def _fetch_proxies(self) -> List[str]:
        url = "https://free-proxy-list.net/"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                html = response.read().decode('utf-8')
        except Exception:
            return []
            
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table', class_='table')
        proxies = []
        
        if table:
            tbody = table.find('tbody')
            if tbody:
                for row in tbody.find_all('tr'):
                    cols = row.find_all('td')
                    if len(cols) >= 7:
                        ip = cols[0].text.strip()
                        port = cols[1].text.strip()
                        is_https = cols[6].text.strip().lower() == 'yes'
                        scheme = 'https' if is_https else 'http'
                        proxies.append(f"{scheme}://{ip}:{port}")
                        
        if not proxies:
            matches = re.findall(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})</td><td>(\d+)', html)
            for ip, port in matches:
                proxies.append(f"http://{ip}:{port}")
                
        return proxies

    def get_proxy(self) -> Optional[str]:
        with self.lock:
            now = time.time()
            if not self.proxies or (now - self.last_fetched > self.cache_ttl):
                fetched = self._fetch_proxies()
                if fetched:
                    self.proxies = fetched
                    self.last_fetched = now
                    self.current_index = 0
            
            if not self.proxies:
                return None
                
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            return proxy

class ProxyConfig:
    """Configuration helper for proxy settings, supporting simulated, free, or real residential proxies."""

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        auto_rotate: bool = False,
        session_id: Optional[str] = None
    ):
        """
        Args:
            proxy_url: The proxy URL in format 'http://user:pass@host:port' or 'http://host:port'.
                       Can contain '{session}' in the username to enable dynamic session generation.
                       Can also be set to 'free-proxy-list' to rotate through free public proxies.
                       Example: 'http://myuser-session-{session}:mypass@localhost:8088'
            auto_rotate: If True, generate a new random session ID for every request if {session} is present.
            session_id: Fixed session ID to use. If None and auto_rotate is False, a static one is generated.
        """
        self.proxy_url = proxy_url
        self.auto_rotate = auto_rotate
        self.session_id = session_id or str(uuid.uuid4())[:8]

    def get_active_proxy_url(self) -> Optional[str]:
        """Resolves the proxy URL, substituting the session placeholder or fetching from free list if present."""
        if not self.proxy_url:
            return None

        if self.proxy_url == "free-proxy-list":
            # Retrieve from free proxy list
            resolved = FreeProxyManager().get_proxy()
            # If unable to fetch, fallback to the local simulated proxy default
            return resolved or "http://127.0.0.1:8088"

        current_session = str(uuid.uuid4())[:8] if self.auto_rotate else self.session_id
        return self.proxy_url.replace("{session}", current_session)

    def to_playwright_proxy(self) -> Optional[Dict[str, Any]]:
        """Converts the resolved proxy URL to Playwright proxy configuration format."""
        active_url = self.get_active_proxy_url()
        if not active_url:
            return None

        parsed = urllib.parse.urlparse(active_url)
        server = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port:
            server += f":{parsed.port}"

        proxy_dict = {"server": server}
        if parsed.username:
            proxy_dict["username"] = parsed.username
        if parsed.password:
            proxy_dict["password"] = parsed.password

        return proxy_dict

