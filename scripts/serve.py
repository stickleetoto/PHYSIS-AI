"""Windows source and portable entry point. Serves the built UI and API together."""
import argparse
from http.client import HTTPException
import json
import ipaddress
import os
from pathlib import Path
import socket
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
HOST = "127.0.0.1"
VERSION = "0.4"


def is_running(address):
    try:
        with urlopen(address + "/api/health", timeout=.6) as response:
            health = json.load(response)
            return (health.get("service") == "PHYSIS AI" and health.get("version") == VERSION
                    and (os.getenv("PHYSIS_OFFLINE") != "1" or health.get("offline") is True))
    except (OSError, URLError, HTTPException, ValueError, AttributeError):
        return False


def open_when_ready(address):
    for _ in range(120):
        if is_running(address):
            webbrowser.open(address)
            return
        time.sleep(.25)

def offline_guard(event, args):
    if event == "socket.getaddrinfo":
        host = args[0]
    elif event == "socket.connect" and isinstance(args[1], tuple):
        host = args[1][0]
    else:
        return
    if host is None or host in {"localhost","::1", "127.0.0.1"}:
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise PermissionError("PHYSIS offline mode allows loopback connections only.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765, choices=range(1, 65536), metavar="PORT")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--offline", action="store_true", help="use local Mock and block external network access")
    args = parser.parse_args()
    if args.offline or os.getenv("PHYSIS_OFFLINE") == "1":
        os.environ["PHYSIS_OFFLINE"] = "1"
        os.environ["PHYSIS_AI_PROVIDER"] = "mock"
        sys.addaudithook(offline_guard)
    address = f"http://{HOST}:{args.port}"
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        sys.exit("UI build missing. Run Setup-Windows.cmd first.")
    try:
        with socket.socket() as probe:
            probe.bind((HOST, args.port))
    except OSError:
        if is_running(address):
            if not args.no_browser:
                webbrowser.open(address)
            print("PHYSIS AI is already running at", address)
            return
        sys.exit(f"Port {args.port} is already in use. Close the other service or run Start-PHYSIS.cmd --port 8766.")
    print(f"Loading PHYSIS AI at {address} ...", flush=True)
    try:
        import uvicorn
        from physis.api import app
    except ImportError as exc:
        sys.exit(f"Runtime dependency missing ({exc}). Run Setup-Windows.cmd.")
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(address,), daemon=True).start()
    print(f"PHYSIS AI {VERSION}  {address}   |   Ctrl+C to stop", flush=True)
    uvicorn.run(app, host=HOST, port=args.port, loop="asyncio", http="h11", ws="none", proxy_headers=False)


if __name__ == "__main__":
    main()
