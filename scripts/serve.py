"""Windows source and portable entry point. Serves the built UI and API together."""
import argparse
from http.client import HTTPException
import json
import ipaddress
import os
from pathlib import Path
import signal
import socket
import struct
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from windows_prerequisites import (  # noqa: E402
    VC_REDIST_DOWNLOAD_URL,
    VC_REDIST_INFO_URL,
    VC_REDIST_MINIMUM_TEXT,
    missing_vc_runtime,
    system32_directory,
)


HOST = "127.0.0.1"
VERSION = "0.4.1"
PACKAGE_LOCK = ROOT / "runtime-lock.json"
PORTABLE_RUNTIME = ROOT / "runtime" / "python.exe"


def is_portable_package():
    return PACKAGE_LOCK.is_file()


def validate_portable_runtime():
    try:
        lock = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"The portable runtime lock is missing or invalid: {exc}") from None
    if not isinstance(lock, dict):
        raise SystemExit("The portable runtime lock must contain a JSON object.")
    product = lock.get("product", {})
    runtime = lock.get("runtime", {})
    installation = lock.get("installation", {})
    if (not isinstance(product, dict) or product.get("version") != VERSION
            or not isinstance(runtime, dict) or runtime.get("architecture") != "win-amd64"
            or not isinstance(installation, dict)
            or installation.get("python_executable", "").replace("\\", "/") != "runtime/python.exe"):
        raise SystemExit("runtime-lock.json does not match this PHYSIS AI Windows x64 release.")
    if not PORTABLE_RUNTIME.is_file():
        raise SystemExit("The portable runtime is not ready. Run Setup-Runtime.cmd explicitly first.")
    actual = os.path.normcase(os.path.abspath(sys.executable))
    expected = os.path.normcase(os.path.abspath(PORTABLE_RUNTIME))
    if actual != expected:
        raise SystemExit("This distribution must be started with its runtime\\python.exe. Run Start-PHYSIS.cmd.")
    expected_python = str(runtime.get("version", ""))
    actual_python = ".".join(map(str, sys.version_info[:3]))
    if not expected_python or expected_python != actual_python or struct.calcsize("P") != 8:
        raise SystemExit("The package requires the exact 64-bit CPython version in runtime-lock.json.")


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
    if host is None or host in {"localhost", "::1", "127.0.0.1"}:
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise PermissionError("PHYSIS offline mode allows loopback connections only.")


def _looks_like_native_dll_error(exc):
    if getattr(exc, "winerror", None) in {126, 127, 193, 1114}:
        return True
    message = str(exc).lower()
    return "dll load failed" in message or "specified module could not be found" in message


def verify_native_dependencies(portable):
    """Load the actual native math stack before opening the local service."""
    try:
        import numpy
        import scipy
        from scipy.linalg import solve
        import fastapi
        import httpx
        import pydantic
        import pypdf
        import sympy
        import uvicorn

        result = solve(numpy.array([[3.0, 1.0], [1.0, 2.0]]), numpy.array([9.0, 8.0]))
        if not numpy.allclose(result, [2.0, 3.0]):
            raise RuntimeError("The bundled NumPy/SciPy native calculation check returned an unexpected result.")
    except (ImportError, OSError, RuntimeError) as exc:
        if portable and _looks_like_native_dll_error(exc):
            diagnostic = missing_vc_runtime(system32_directory(), [ROOT / "runtime"])
            if diagnostic:
                raise SystemExit(diagnostic) from None
        if portable:
            hint = "Run Setup-Runtime.cmd again and review its dependency check."
        else:
            hint = "Run Setup-Windows.cmd to create or repair the source environment."
        raise SystemExit(f"A required PHYSIS AI runtime dependency could not be loaded ({type(exc).__name__}). {hint}") from None


def main():
    portable = is_portable_package()
    if portable:
        validate_portable_runtime()
    elif (ROOT / "Setup-Runtime.cmd").is_file():
        raise SystemExit("This package is incomplete because runtime-lock.json is missing. Extract the distribution ZIP again.")

    if not os.getenv("PHYSIS_AI_PROVIDER"):
        os.environ["PHYSIS_AI_PROVIDER"] = "mock"
    if not os.getenv("PHYSIS_ALLOW_ENV_PROVIDER_DEFAULT"):
        os.environ["PHYSIS_ALLOW_ENV_PROVIDER_DEFAULT"] = "0"

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765, choices=range(1, 65536), metavar="PORT")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--offline", action="store_true", help="use local Mock and block external network access")
    args = parser.parse_args()
    if args.offline or os.getenv("PHYSIS_OFFLINE") == "1":
        os.environ["PHYSIS_OFFLINE"] = "1"
        os.environ["PHYSIS_AI_PROVIDER"] = "mock"
        os.environ["PHYSIS_ALLOW_ENV_PROVIDER_DEFAULT"] = "0"
        sys.addaudithook(offline_guard)
    address = f"http://{HOST}:{args.port}"
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        if portable:
            sys.exit("The distribution is missing its built UI. Extract the complete release ZIP again.")
        sys.exit("UI build missing. Run Setup-Windows.cmd first.")
    try:
        with socket.socket() as probe:
            probe.bind((HOST, args.port))
    except OSError:
        if is_running(address):
            if not args.no_browser:
                webbrowser.open(address)
            print("PHYSIS AI is already running at", address, flush=True)
            return
        sys.exit(f"Port {args.port} is already in use. Close that service or choose another free port with: "
                 f"Start-PHYSIS.cmd --port <port> --no-browser")
    print(f"Loading PHYSIS AI at {address} ...", flush=True)
    try:
        verify_native_dependencies(portable)
        from physis.api import app
        import uvicorn
    except ImportError as exc:
        if portable:
            sys.exit(f"Runtime dependency missing ({exc}). Run Setup-Runtime.cmd.")
        sys.exit(f"Runtime dependency missing ({exc}). Run Setup-Windows.cmd.")
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(address,), daemon=True).start()
    print(f"PHYSIS AI {VERSION}  {address}   |   Ctrl+C / Ctrl+Break to stop", flush=True)
    previous_break_handler = None
    if hasattr(signal, "SIGBREAK"):
        previous_break_handler = signal.getsignal(signal.SIGBREAK)
        signal.signal(signal.SIGBREAK, lambda signum, frame: signal.raise_signal(signal.SIGINT))
    try:
        uvicorn.run(app, host=HOST, port=args.port, loop="asyncio", http="h11", ws="none", proxy_headers=False)
    finally:
        if previous_break_handler is not None:
            signal.signal(signal.SIGBREAK, previous_break_handler)


if __name__ == "__main__":
    main()
