import socket
import select
import threading
import sys
import argparse
import base64
import hashlib
import random
from typing import Tuple, Dict, Any

# A database of simulated country/ISP data to make the mock residential proxy experience highly realistic.
COUNTRIES_DB = [
    {
        "country": "United States",
        "code": "US",
        "cities": ["New York", "Los Angeles", "Chicago", "Miami", "San Francisco", "Austin", "Seattle"],
        "isps": ["Comcast Cable", "AT&T Internet", "Spectrum", "Verizon Fios", "Cox Communications"]
    },
    {
        "country": "United Kingdom",
        "code": "GB",
        "cities": ["London", "Manchester", "Birmingham", "Leeds", "Glasgow", "Bristol", "Edinburgh"],
        "isps": ["BT Broadband", "Virgin Media", "Sky Broadband", "TalkTalk", "EE"]
    },
    {
        "country": "Philippines",
        "code": "PH",
        "cities": ["Manila", "Quezon City", "Davao", "Cebu", "Makati", "Pasig", "Taguig"],
        "isps": ["PLDT Home Fibr", "Globe Telecom", "Converge ICT Solutions", "Dito Telecommunity"]
    },
    {
        "country": "Germany",
        "code": "DE",
        "cities": ["Berlin", "Munich", "Frankfurt", "Hamburg", "Cologne", "Dusseldorf", "Stuttgart"],
        "isps": ["Deutsche Telekom", "Vodafone Deutschland", "1&1 Telecom", "O2 DSL"]
    },
    {
        "country": "Canada",
        "code": "CA",
        "cities": ["Toronto", "Vancouver", "Montreal", "Calgary", "Ottawa", "Edmonton", "Halifax"],
        "isps": ["Rogers Communications", "Bell Canada", "Telus", "Shaw Communications", "Videotron"]
    },
    {
        "country": "Australia",
        "code": "AU",
        "cities": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Canberra"],
        "isps": ["Telstra", "Optus", "TPG", "iiNet", "Aussie Broadband"]
    },
    {
        "country": "Japan",
        "code": "JP",
        "cities": ["Tokyo", "Osaka", "Kyoto", "Yokohama", "Nagoya", "Fukuoka"],
        "isps": ["NTT Docomo", "SoftBank BB", "KDDI", "So-net"]
    }
]

# Thread-safe dictionary to cache generated IP info for sessions so they act like "sticky" sessions
session_cache = {}
cache_lock = threading.Lock()

def get_simulated_residential_ip(username: str) -> Dict[str, Any]:
    """
    Deterministically generates simulated residential IP details based on the username string.
    This guarantees that the same session/username always gets the exact same IP and location details
    (simulating "sticky sessions"), while different sessions get different IPs.
    """
    # Extract session identifier from username (e.g. user-session-1234 -> 1234)
    session_key = username
    if "-session-" in username:
        session_key = username.split("-session-")[-1]
    elif "session-" in username:
        session_key = username.split("session-")[-1]

    with cache_lock:
        if session_key in session_cache:
            return session_cache[session_key]

        # Use MD5 hash of session_key to seed the random generator for this session
        seed = int(hashlib.md5(session_key.encode('utf-8')).hexdigest(), 16)
        rng = random.Random(seed)

        # Generate a realistic public IP address (avoiding private ranges)
        while True:
            first_octet = rng.randint(1, 223)
            if first_octet not in (10, 127, 169, 172, 192):
                break
        ip = f"{first_octet}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"

        country_data = rng.choice(COUNTRIES_DB)
        city = rng.choice(country_data["cities"])
        isp = rng.choice(country_data["isps"])
        
        ip_info = {
            "ip": ip,
            "country": country_data["country"],
            "country_code": country_data["code"],
            "city": city,
            "isp": isp,
            "session_id": session_key
        }
        session_cache[session_key] = ip_info
        return ip_info

class ThreadedProxyServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8088):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def start(self):
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(100)
            print("=" * 80)
            print(f" [SIMULATED RESIDENTIAL PROXY SERVER RUNNING]")
            print(f" Address: http://{self.host}:{self.port}")
            print(f" Status:  Simulated / Dud Mode active.")
            print(f" Mode:    Auto-generates residential info from usernames / sessions.")
            print("=" * 80)
            
            while True:
                client_conn, client_addr = self.server_socket.accept()
                thread = threading.Thread(
                    target=self.handle_client, 
                    args=(client_conn, client_addr),
                    daemon=True
                )
                thread.start()
        except KeyboardInterrupt:
            print("\nShutting down simulated proxy server...")
        except OSError as e:
            # WinError 10038 or similar is expected when socket is closed from another thread to terminate the server.
            # We only print the error if it wasn't an intentional shutdown.
            pass
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            try:
                self.server_socket.close()
            except Exception:
                pass


    def handle_client(self, client_conn: socket.socket, client_addr: Tuple[str, int]):
        try:
            # Read initial headers from the client
            request_data = b""
            while b"\r\n\r\n" not in request_data and len(request_data) < 8192:
                chunk = client_conn.recv(1024)
                if not chunk:
                    break
                request_data += chunk

            if not request_data:
                client_conn.close()
                return

            headers_part = request_data.split(b"\r\n\r\n")[0]
            header_lines = headers_part.decode('utf-8', errors='ignore').split('\r\n')
            
            if not header_lines or not header_lines[0]:
                client_conn.close()
                return

            first_line = header_lines[0]
            parts = first_line.split(' ')
            if len(parts) < 3:
                client_conn.close()
                return
            
            method, target, version = parts[0], parts[1], parts[2]
            
            # Extract proxy authorization credentials if present
            username = "default_user"
            for line in header_lines[1:]:
                if line.lower().startswith("proxy-authorization:"):
                    try:
                        auth_type, credentials = line.split(":", 1)[1].strip().split(" ", 1)
                        if auth_type.lower() == "basic":
                            decoded = base64.b64decode(credentials).decode('utf-8')
                            if ":" in decoded:
                                username, _ = decoded.split(":", 1)
                    except Exception:
                        pass
                    break

            # Fetch the simulated residential IP information
            ip_info = get_simulated_residential_ip(username)
            print(f"\n[PROXY REQUEST] Session: {ip_info['session_id']}")
            print(f"  +-- Client Address: {client_addr[0]}:{client_addr[1]}")
            print(f"  +-- Simulated Exit IP: {ip_info['ip']} ({ip_info['isp']} - {ip_info['city']}, {ip_info['country_code']})")
            print(f"  +-- Request: {method} {target}")

            if method == "CONNECT":
                self.handle_connect(client_conn, target, request_data, ip_info)
            else:
                self.handle_http(client_conn, method, target, version, header_lines, request_data, ip_info)
                
        except Exception as e:
            print(f"[ERROR] Error handling connection: {e}")
            try:
                client_conn.close()
            except Exception:
                pass

    def handle_connect(self, client_conn: socket.socket, target: str, request_data: bytes, ip_info: dict):
        """Handles HTTPS tunneling using the CONNECT method."""
        try:
            if ":" in target:
                host, port_str = target.split(":", 1)
                port = int(port_str)
            else:
                host = target
                port = 443

            # Connect to target server
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.settimeout(10.0)
            target_socket.connect((host, port))
            
            # Send connection established back to the client
            client_conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            
            # Start bidirectional tunneling
            self.tunnel(client_conn, target_socket)
            print(f"  +-- Tunnel closed for {host}:{port}")
        except Exception as e:
            print(f"  +-- CONNECT failed to {target}: {e}")
            try:
                client_conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            except Exception:
                pass
            client_conn.close()

    def handle_http(self, client_conn: socket.socket, method: str, target: str, version: str, 
                    header_lines: list, request_data: bytes, ip_info: dict):
        """Handles standard HTTP requests by forwarding them."""
        target_socket = None
        try:
            # Parse target URL
            url = target
            if url.startswith("http://"):
                url = url[7:]
            elif url.startswith("https://"):
                url = url[8:]
                
            path = "/"
            if "/" in url:
                host_port, path = url.split("/", 1)
                path = "/" + path
            else:
                host_port = url

            if ":" in host_port:
                host, port_str = host_port.split(":", 1)
                port = int(port_str)
            else:
                host = host_port
                port = 80

            # Rebuild request headers, stripping Proxy headers
            new_headers = []
            new_headers.append(f"{method} {path} {version}")
            
            for line in header_lines[1:]:
                # Strip proxy specific headers
                if line.lower().startswith("proxy-"):
                    continue
                new_headers.append(line)

            # Add Simulated Proxy information header just for traceability!
            new_headers.append(f"X-Simulated-Residential-IP: {ip_info['ip']}")
            new_headers.append(f"X-Simulated-Country: {ip_info['country_code']}")
            
            rebuilt_request = "\r\n".join(new_headers) + "\r\n\r\n"
            
            # Forward to target server
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.settimeout(10.0)
            target_socket.connect((host, port))
            target_socket.sendall(rebuilt_request.encode('utf-8'))
            
            # Read response and forward back to client
            while True:
                response_data = target_socket.recv(4096)
                if not response_data:
                    break
                client_conn.sendall(response_data)
                
            print(f"  +-- HTTP Request forwarded successfully to {host}:{port}")
        except Exception as e:
            print(f"  +-- HTTP Forward failed to {target}: {e}")
            try:
                client_conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            except Exception:
                pass
        finally:
            if target_socket:
                target_socket.close()
            client_conn.close()

    def tunnel(self, client_conn: socket.socket, target_socket: socket.socket):
        """Tunnels raw TCP traffic bidirectionally."""
        sockets = [client_conn, target_socket]
        keep_running = True
        while keep_running:
            try:
                readable, _, exceptional = select.select(sockets, [], sockets, 20.0)
                if exceptional:
                    break
                if not readable:
                    # Timeout
                    break
                
                for sock in readable:
                    data = sock.recv(16384)
                    if not data:
                        keep_running = False
                        break
                    
                    if sock is client_conn:
                        target_socket.sendall(data)
                    else:
                        client_conn.sendall(data)
            except Exception:
                break
        
        try:
            client_conn.close()
        except Exception:
            pass
        try:
            target_socket.close()
        except Exception:
            pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulated Residential Proxy Server for Scraper Testing")
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind to")
    parser.add_argument("--port", type=int, default=8088, help="Port to listen on")
    args = parser.parse_args()
    
    server = ThreadedProxyServer(args.host, args.port)
    server.start()
