"""Smoke a PHYSIS AI Windows distribution from its actual extracted ZIP.

Run from a Windows host with a host-side Python 3.10+ and only the standard library:
    python scripts/verify_windows_distribution.py --zip release/PHYSIS-AI-0.4.1-win-x64.zip \
        --work-dir C:\\temp\\physis-smoke-new --report release\\windows-smoke.json

The ZIP mode tests the missing-runtime message, invokes the explicit runtime setup,
then exercises the real bundled interpreter through the localhost launcher. App mode
is for an already-extracted and provisioned app and reports archive/setup as NOT RUN.
"""
import argparse
import atexit
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile


EXPECTED_APP_VERSION = "0.4.1"
APP_ARCHIVE_ROOT = "PHYSIS-AI"
HOST = "127.0.0.1"
ACTIVE_PROCESSES = {}


class SmokeFailure(RuntimeError):
    pass


class _JobBasic(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class _JobIoCounters(ctypes.Structure):
    _fields_ = [("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64)]


class _JobExtended(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _JobBasic),
                ("IoInfo", _JobIoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sanitize(value, *private_paths):
    text = str(value)
    for path in private_paths:
        if path:
            text = text.replace(str(path), "<STAGING>")
            try:
                text = text.replace(str(Path(path).resolve()), "<STAGING>")
            except OSError:
                pass
    text = re.sub(r"(?i)[A-Z]:\\Users\\[^\\\s]+", "<USER_PATH>", text)
    text = re.sub(r"(?i)[A-Z]:\\(?:Windows\\)?Temp\\[^\\\s]+", "<TEMP_PATH>", text)
    return text


def make_work_dir(requested):
    if requested is None:
        return Path(tempfile.mkdtemp(prefix="physis-ai-distribution-smoke-"))
    root = requested.expanduser().absolute()
    if root.exists():
        if not root.is_dir() or any(root.iterdir()):
            raise SmokeFailure("--work-dir must name a new or empty directory.")
    else:
        root.mkdir(parents=True)
    return root


def extract_zip_safely(archive_path, destination):
    archive_path = Path(archive_path).expanduser().resolve()
    if not archive_path.is_file():
        raise SmokeFailure("The requested distribution ZIP does not exist.")
    destination.mkdir(parents=True, exist_ok=False)
    try:
        with ZipFile(archive_path) as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise SmokeFailure("The distribution ZIP failed its CRC check.")
            names = set()
            for member in archive.infolist():
                name = member.filename
                path = PurePosixPath(name)
                if (not name or "\\" in name or ":" in name or path.is_absolute()
                        or any(part in {"", ".", ".."} for part in path.parts)
                        or path.parts[0] != APP_ARCHIVE_ROOT):
                    raise SmokeFailure("The distribution ZIP contains an unsafe or unexpected member path.")
                if name in names:
                    raise SmokeFailure("The distribution ZIP contains a duplicate member path.")
                names.add(name)
                mode = (member.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise SmokeFailure("The distribution ZIP contains a symbolic link.")
                target = destination.joinpath(*path.parts)
                resolved_destination = destination.resolve()
                resolved_target = target.resolve()
                if os.path.commonpath((str(resolved_destination), str(resolved_target))) != str(resolved_destination):
                    raise SmokeFailure("The distribution ZIP contains a member outside its extraction folder.")
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    except (BadZipFile, OSError, ValueError) as exc:
        if isinstance(exc, SmokeFailure):
            raise
        raise SmokeFailure(f"The distribution ZIP could not be extracted ({type(exc).__name__}).") from None
    app_root = destination / APP_ARCHIVE_ROOT
    for required in ("Start-PHYSIS.cmd", "runtime-lock.json", "Setup-Runtime.cmd", "Setup-Runtime.ps1"):
        if not (app_root / required).is_file():
            raise SmokeFailure(f"The extracted distribution is missing required root entry: {required}.")
    return app_root


def _windows_paths(include_powershell=False):
    system_root = Path(os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows")
    paths = [system_root / "System32"]
    if include_powershell:
        paths.extend((system_root / "System32" / "WindowsPowerShell" / "v1.0",
                      system_root / "System32" / "wbem"))
    return system_root, paths


def clean_windows_env(work_dir, app_root, *, setup=False):
    system_root, windows_paths = _windows_paths(include_powershell=setup)
    system32 = system_root / "System32"
    env = {
        "SystemRoot": str(system_root),
        "WINDIR": str(system_root),
        "COMSPEC": str(system32 / "cmd.exe"),
        "PATHEXT": ".COM;.EXE;.BAT;.CMD",
        "PATH": os.pathsep.join(str(path) for path in windows_paths),
        "TEMP": str(work_dir / "temp"),
        "TMP": str(work_dir / "temp"),
        "LOCALAPPDATA": str(work_dir / "local-app-data"),
        "USERPROFILE": str(work_dir / "profile"),
        "PHYSIS_DATA_DIR": str(work_dir / "user-data"),
        "PHYSIS_AI_PROVIDER": "mock",
        "PHYSIS_ALLOW_ENV_PROVIDER_DEFAULT": "0",
        "PHYSIS_OFFLINE": "1",
        "PHYSIS_NO_PAUSE": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    for name in ("PROCESSOR_ARCHITECTURE", "PROCESSOR_ARCHITEW6432", "PROCESSOR_IDENTIFIER",
                 "PROCESSOR_LEVEL", "PROCESSOR_REVISION"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    for path in (work_dir / "temp", work_dir / "local-app-data", work_dir / "profile", work_dir / "user-data"):
        path.mkdir(parents=True, exist_ok=True)
    return env


class _JobObject:
    """Own and, only as a fallback, terminate the test process tree."""

    def __init__(self, process):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.handle = None
        self.kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int,
                                                        ctypes.c_void_p, wintypes.DWORD)
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.kernel.CloseHandle.restype = wintypes.BOOL
        handle = self.kernel.CreateJobObjectW(None, None)
        if not handle:
            return
        info = _JobExtended()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.kernel.CloseHandle(handle)
            return
        if not self.kernel.AssignProcessToJobObject(handle, wintypes.HANDLE(int(process._handle))):
            self.kernel.CloseHandle(handle)
            return
        self.handle = handle

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


_PRIVATE_CONSOLE_HELPER = r'''import ctypes, sys, time
from ctypes import wintypes

mode, target_pid, argument = sys.argv[1], int(sys.argv[2]), sys.argv[3]
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.FreeConsole.restype = wintypes.BOOL
kernel.AttachConsole.argtypes = (wintypes.DWORD,)
kernel.AttachConsole.restype = wintypes.BOOL
kernel.SetConsoleCtrlHandler.argtypes = (ctypes.c_void_p, wintypes.BOOL)
kernel.SetConsoleCtrlHandler.restype = wintypes.BOOL
kernel.GenerateConsoleCtrlEvent.argtypes = (wintypes.DWORD, wintypes.DWORD)
kernel.GenerateConsoleCtrlEvent.restype = wintypes.BOOL

# This helper is launched with DETACHED_PROCESS so attaching it cannot also
# attach or deliver the event to the smoke harness itself.
kernel.FreeConsole()
if not kernel.AttachConsole(target_pid):
    raise ctypes.WinError(ctypes.get_last_error())

if mode == "signal":
    handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
    @handler_type
    def ignore_our_own_event(_event):
        return True
    if not kernel.SetConsoleCtrlHandler(ignore_our_own_event, True):
        raise ctypes.WinError(ctypes.get_last_error())
    event = 0 if argument == "ctrl_c" else 1
    if not kernel.GenerateConsoleCtrlEvent(event, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    time.sleep(0.2)  # Keep the true handler alive while Windows dispatches the event.
elif mode == "answer":
    class CharUnion(ctypes.Union):
        _fields_ = [("UnicodeChar", ctypes.c_wchar), ("AsciiChar", ctypes.c_char)]
    class KeyEvent(ctypes.Structure):
        _fields_ = [("bKeyDown", wintypes.BOOL), ("wRepeatCount", wintypes.WORD),
                    ("wVirtualKeyCode", wintypes.WORD), ("wVirtualScanCode", wintypes.WORD),
                    ("uChar", CharUnion), ("dwControlKeyState", wintypes.DWORD)]
    class EventUnion(ctypes.Union):
        _fields_ = [("KeyEvent", KeyEvent), ("padding", ctypes.c_byte * 16)]
    class InputRecord(ctypes.Structure):
        _fields_ = [("EventType", wintypes.WORD), ("Event", EventUnion)]
    kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.WriteConsoleInputW.argtypes = (wintypes.HANDLE, ctypes.POINTER(InputRecord),
                                          wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    kernel.WriteConsoleInputW.restype = wintypes.BOOL
    console_in = kernel.CreateFileW("CONIN$", 0xC0000000, 3, None, 3, 0, None)
    if console_in == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    records = (InputRecord * 4)()
    for index, (key, char, down) in enumerate(((0x59, "y", True), (0x59, "y", False),
                                                (0x0D, "\r", True), (0x0D, "\r", False))):
        records[index].EventType = 1  # KEY_EVENT
        records[index].Event.KeyEvent = KeyEvent(down, 1, key, 0, CharUnion(UnicodeChar=char), 0)
    written = wintypes.DWORD()
    try:
        if not kernel.WriteConsoleInputW(console_in, records, len(records), ctypes.byref(written)):
            raise ctypes.WinError(ctypes.get_last_error())
        if written.value != len(records):
            raise RuntimeError("The console accepted only part of the confirmation input.")
    finally:
        kernel.CloseHandle(console_in)
else:
    raise ValueError("Unknown private console helper mode.")
kernel.FreeConsole()
'''


def _run_private_console_helper(process, mode, argument, *, timeout=10):
    if process.poll() is not None:
        return
    system_root, _ = _windows_paths()
    helper_env = {
        "SystemRoot": str(system_root),
        "WINDIR": str(system_root),
        "PATH": str(system_root / "System32"),
        "TEMP": os.environ.get("TEMP", str(system_root / "Temp")),
        "TMP": os.environ.get("TMP", os.environ.get("TEMP", str(system_root / "Temp"))),
        "PYTHONUTF8": "1",
    }
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", _PRIVATE_CONSOLE_HELPER,
             mode, str(process.pid), argument],
            env=helper_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.DETACHED_PROCESS,
            close_fds=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise SmokeFailure("The detached private-console helper timed out.") from None
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace")[-500:]
        raise SmokeFailure(f"The detached private-console helper failed ({result.returncode}): {detail}")


def send_console_signal_to_private_console(process, kind="ctrl_break"):
    """Send Ctrl+C or Ctrl+Break from a detached helper to this test console only."""
    _run_private_console_helper(process, "signal", kind)


def answer_batch_termination_prompt(process):
    """Acknowledge cmd.exe's Ctrl+C prompt after the child server has stopped."""
    _run_private_console_helper(process, "answer", "y")


def _make_hidden_process(command, cwd, env, log_path):
    system_root, _ = _windows_paths()
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            startupinfo=startup,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            close_fds=True,
        )
    job = _JobObject(process)
    ACTIVE_PROCESSES[process] = (job, env)
    return process, job


def _scoped_force_cleanup(process, job, env):
    if job and job.handle:
        job.close()
    elif process.poll() is None:
        system_root, _ = _windows_paths()
        taskkill = system_root / "System32" / "taskkill.exe"
        try:
            subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                           env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=15, check=False)
        except subprocess.SubprocessError:
            pass
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pass
    ACTIVE_PROCESSES.pop(process, None)


def _read_log(path, *private_paths):
    try:
        return sanitize(Path(path).read_text(encoding="utf-8", errors="replace"), *private_paths)
    except OSError:
        return ""


def run_short_command(command, cwd, env, log_path, timeout):
    process, job = _make_hidden_process(command, cwd, env, log_path)
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _scoped_force_cleanup(process, job, env)
        raise SmokeFailure(f"A short Windows command timed out after {timeout} seconds.") from None
    else:
        if job:
            job.close()
        ACTIVE_PROCESSES.pop(process, None)
    return code, _read_log(log_path, cwd)


class RunningServer:
    def __init__(self, process, job, log_path, address, env, app_root):
        self.process = process
        self.job = job
        self.log_path = log_path
        self.address = address
        self.env = env
        self.app_root = app_root
        self.batch_prompt_acknowledged = False

    def stop(self, kind="ctrl_break"):
        if self.process.poll() is not None:
            if port_accepts_connections(self.address[0], self.address[1], timeout=.4):
                _scoped_force_cleanup(self.process, self.job, self.env)
                raise SmokeFailure("The launcher exited while a server still owned its test port.")
            if self.job:
                self.job.close()
            ACTIVE_PROCESSES.pop(self.process, None)
            return self.process.returncode
        try:
            send_console_signal_to_private_console(self.process, kind)
            deadline = time.monotonic() + 25
            while self.process.poll() is None and port_accepts_connections(
                    self.address[0], self.address[1], timeout=.2):
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(self.process.args, 25)
                time.sleep(.1)
            if self.process.poll() is None:
                # The Python server has closed its listener. cmd.exe may still be
                # waiting at its localized "Terminate batch job?" prompt after
                # CTRL_C_EVENT; answer only after the service is confirmed down.
                time.sleep(.2)
                if self.process.poll() is None:
                    answer_batch_termination_prompt(self.process)
                    self.batch_prompt_acknowledged = True
            self.process.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired, SmokeFailure) as exc:
            _scoped_force_cleanup(self.process, self.job, self.env)
            raise SmokeFailure(f"The server did not stop through {kind.upper()} ({type(exc).__name__}).") from None
        if port_accepts_connections(self.address[0], self.address[1], timeout=.4):
            _scoped_force_cleanup(self.process, self.job, self.env)
            raise SmokeFailure(f"The server process exited but its test port remained open after {kind.upper()}.")
        if "Application shutdown complete" not in self.log_text():
            if self.job:
                self.job.close()
            ACTIVE_PROCESSES.pop(self.process, None)
            raise SmokeFailure(f"The server exited after {kind.upper()} without evidence of graceful application shutdown.")
        if self.job:
            self.job.close()
        ACTIVE_PROCESSES.pop(self.process, None)
        return self.process.returncode

    def log_text(self):
        return _read_log(self.log_path, self.app_root)


def _free_port():
    for _ in range(30):
        candidate = 20000 + int.from_bytes(os.urandom(2), "big") % 20000
        with socket.socket() as probe:
            try:
                probe.bind((HOST, candidate))
                return candidate
            except OSError:
                pass
    raise SmokeFailure("Could not reserve a localhost test port.")


def port_accepts_connections(host, port, timeout=.2):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def start_server(app_root, port, work_dir, log_name):
    env = clean_windows_env(work_dir, app_root)
    address = (HOST, port)
    log_path = work_dir / "logs" / log_name
    command = [env["COMSPEC"], "/d", "/c", "Start-PHYSIS.cmd",
               "--port", str(port), "--no-browser", "--offline"]
    process, job = _make_hidden_process(command, app_root, env, log_path)
    server = RunningServer(process, job, log_path, address, env, app_root)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SmokeFailure("The packaged launcher exited before health became ready: " + server.log_text()[-1600:])
        try:
            health = get_json(f"http://{HOST}:{port}/api/health", timeout=1.0)
            if health.get("service") == "PHYSIS AI":
                return server, health
        except (OSError, URLError, HTTPError, ValueError):
            time.sleep(.2)
    try:
        server.stop()
    except SmokeFailure:
        pass
    raise SmokeFailure("The packaged launcher did not become healthy within 120 seconds: " + server.log_text()[-1600:])


def get_json(url, timeout=10):
    with urlopen(url, timeout=timeout) as response:
        return json.load(response)


def post_json(url, body, timeout=40):
    request = Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def post_ndjson(url, body, timeout=90):
    request = Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:
        records = [json.loads(line) for line in response.read().decode("utf-8").splitlines() if line.strip()]
    result = next((record["result"] for record in reversed(records) if record.get("event") == "result"), None)
    if result is None:
        errors = [record.get("detail") for record in records if record.get("event") == "error"]
        raise SmokeFailure("The Tutor stream did not produce a final result: " + (errors[-1] if errors else "no result event"))
    return records, result


def verify_runtime(app_root, env, log_path):
    try:
        lock = json.loads((app_root / "runtime-lock.json").read_text(encoding="utf-8"))
        expected_python = str(lock["runtime"]["version"])
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        raise SmokeFailure("runtime-lock.json does not contain an expected Python version.") from None
    command = [str(app_root / "runtime" / "python.exe"), "-I", "-c",
               "import json,struct,sys,numpy,scipy,fastapi,pydantic,uvicorn,sympy,pypdf,httpx; "
               "from scipy.linalg import solve; "
               "x=solve(numpy.array([[3.0,1.0],[1.0,2.0]]),numpy.array([9.0,8.0])); "
               "assert numpy.allclose(x,[2.0,3.0]); "
               "print(json.dumps({'python':'.'.join(map(str,sys.version_info[:3])),"
               "'bits':struct.calcsize('P')*8,'numpy':numpy.__version__,'scipy':scipy.__version__}))"]
    code, log = run_short_command(command, app_root, env, log_path, timeout=120)
    if code != 0:
        raise SmokeFailure("The embedded runtime or native dependency load check failed: " + log[-1800:])
    lines = [line for line in log.splitlines() if line.startswith("{")]
    if not lines:
        raise SmokeFailure("The embedded runtime did not report its version and native load check.")
    facts = json.loads(lines[-1])
    architecture = lock.get("runtime", {}).get("architecture")
    facts["architecture"] = architecture
    if (facts.get("python") != expected_python or facts.get("bits") != 64
            or architecture != "win-amd64"):
        raise SmokeFailure("The embedded runtime version or architecture does not match the lock expectation.")
    return facts


def test_missing_vc_redist_diagnostic(app_root, work_dir):
    scripts = str(app_root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import windows_prerequisites

    fake_root = work_dir / "simulated-absent-vc-redist"
    fake_system32 = fake_root / "empty-system32"
    fake_runtime = fake_root / "empty-app-local-runtime"
    fake_system32.mkdir(parents=True)
    fake_runtime.mkdir(parents=True)
    message = windows_prerequisites.missing_vc_runtime(fake_system32, [fake_runtime])
    if (not message or windows_prerequisites.VC_REDIST_MINIMUM_TEXT not in message
            or windows_prerequisites.VC_REDIST_DOWNLOAD_URL not in message):
        raise SmokeFailure("An empty simulated System32/app-local DLL set did not produce the VC Redist diagnostic.")
    return "SIMULATED: empty System32 and app-local test folders produce the official x64 minimum-version diagnostic; host files were not changed."


def test_archive_runtime_absence(app_root, work_dir):
    if (app_root / "runtime" / "python.exe").exists():
        raise SmokeFailure("The ZIP unexpectedly includes runtime/python.exe before the explicit setup step.")
    port = _free_port()
    env = clean_windows_env(work_dir, app_root)
    code, output = run_short_command(
        [env["COMSPEC"], "/d", "/c", "Start-PHYSIS.cmd", "--port", str(port), "--no-browser", "--offline"],
        app_root, env, work_dir / "logs" / "before-setup.log", timeout=20)
    if code == 0 or "Setup-Runtime.cmd" not in output:
        raise SmokeFailure("The launcher did not clearly require explicit Setup-Runtime.cmd before runtime use: " + output[-1200:])
    if (app_root / "runtime" / "python.exe").exists():
        raise SmokeFailure("Starting PHYSIS AI created the runtime automatically; explicit setup was bypassed.")
    return "PASS: the extracted package reported the explicit setup step and did not create or locate a fallback interpreter."


def test_foreign_port_collision(app_root, work_dir):
    with socket.socket() as held:
        held.bind((HOST, 0))
        held.listen(1)
        port = held.getsockname()[1]
        env = clean_windows_env(work_dir, app_root)
        code, output = run_short_command(
            [env["COMSPEC"], "/d", "/c", "Start-PHYSIS.cmd", "--port", str(port), "--no-browser", "--offline"],
            app_root, env, work_dir / "logs" / "foreign-port-collision.log", timeout=20)
    if code == 0 or "already in use" not in output.lower() or "--port <port>" not in output:
        raise SmokeFailure("A foreign listener collision did not return a clear alternative-port instruction: " + output[-1200:])
    return "PASS: a foreign listener is left untouched and the launcher exits with a choose-another-port instruction."


def test_api_and_restart(app_root, work_dir, report):
    port = _free_port()
    address = f"http://{HOST}:{port}"
    server, health = start_server(app_root, port, work_dir, "server-first.log")
    try:
        if health.get("version") != EXPECTED_APP_VERSION:
            raise SmokeFailure(f"Health version was {health.get('version')!r}, expected {EXPECTED_APP_VERSION}.")
        if health.get("provider") != "mock" or health.get("offline") is not True:
            raise SmokeFailure("The packaged server did not start with Mock and offline mode enabled.")
        with urlopen(address + "/", timeout=10) as response:
            page = response.read().decode("utf-8", errors="replace")
            if response.status != 200 or 'id="root"' not in page:
                raise SmokeFailure("The package UI root did not return its built frontend document.")

        experiment = post_json(address + "/api/experiments", {"model": "free_fall"})
        run = experiment.get("run", {})
        if run.get("status") not in {"VERIFIED", "LIMITED"} or not run.get("times") or not run.get("series"):
            raise SmokeFailure("The packaged physics API did not return a checked free-fall run.")
        experiment_id = experiment["experiment"]["id"]
        if abs(run.get("facts", {}).get("arrival_time", 0) - 2.019275) > .00002:
            raise SmokeFailure("The packaged free-fall calculation did not match the expected measured result.")

        math_result = post_json(address + "/api/math", {"operation": "differentiate", "expression": "x^3"})
        if math_result.get("result") != "3*x**2":
            raise SmokeFailure("The packaged symbolic math worker did not return the expected derivative.")

        records, tutor_result = post_ndjson(address + "/api/tutor/stream", {
            "experiment_id": experiment_id,
            "revision": experiment["revision"],
            "message": "현재 실험 결과를 설명해 주세요.",
        })
        if tutor_result.get("snapshot", {}).get("experiment", {}).get("id") != experiment_id:
            raise SmokeFailure("The packaged Tutor did not preserve the active experiment identity.")
        if not tutor_result.get("message") or not any(record.get("event") == "result" for record in records):
            raise SmokeFailure("The packaged Tutor stream returned no explanatory result.")

        database = work_dir / "user-data" / "experiments.sqlite3"
        if not database.is_file() or database.stat().st_size == 0:
            raise SmokeFailure("The packaged API did not persist its experiment database in the isolated data folder.")
        report["checks"].append({"name": "math_physics_tutor_and_localhost", "status": "PASS",
                                 "details": "UI, offline Mock health, free-fall physics, symbolic derivative, and Tutor stream returned expected local results."})
        stop_code = server.stop("ctrl_c")
        ctrl_c_prompt_acknowledged = server.batch_prompt_acknowledged
        server = None
        if stop_code not in (0, 1):
            raise SmokeFailure(f"CTRL+C shutdown returned unexpected code {stop_code}.")
        if port_accepts_connections(HOST, port, timeout=.4):
            raise SmokeFailure("The localhost service still accepted connections after CTRL+C shutdown.")
        report["checks"].append({"name": "ctrl_c_shutdown", "status": "PASS",
                                 "details": "A detached sender delivered CTRL_C_EVENT; Uvicorn logged graceful application shutdown and the port closed."
                                 + (" The harness acknowledged cmd.exe's batch termination prompt after the listener closed."
                                    if ctrl_c_prompt_acknowledged else "")})

        server, restarted_health = start_server(app_root, port, work_dir, "server-restart.log")
        if restarted_health.get("version") != EXPECTED_APP_VERSION or restarted_health.get("offline") is not True:
            raise SmokeFailure("The packaged server did not restart on the released port in offline mode.")
        recovered = get_json(address + f"/api/experiments/{experiment_id}")
        if (recovered.get("experiment") != experiment.get("experiment")
                or recovered.get("revision") != experiment.get("revision")):
            raise SmokeFailure("The saved physics experiment did not survive a packaged server restart.")
        report["checks"].append({"name": "persistence_restart_and_port_reuse", "status": "PASS",
                                 "details": "The same port restarted after shutdown and the saved experiment reloaded with the same ID, inputs, and revision."})
        stop_code = server.stop("ctrl_break")
        ctrl_break_prompt_acknowledged = server.batch_prompt_acknowledged
        server = None
        if stop_code not in (0, 1) or port_accepts_connections(HOST, port, timeout=.4):
            raise SmokeFailure("The restarted server did not shut down cleanly or release its port.")
        report["checks"].append({"name": "ctrl_break_shutdown", "status": "PASS",
                                 "details": "A detached sender delivered CTRL_BREAK_EVENT; Uvicorn logged graceful application shutdown and the same port closed."
                                 + (" The harness acknowledged cmd.exe's batch termination prompt after the listener closed."
                                    if ctrl_break_prompt_acknowledged else "")})
    finally:
        if server is not None:
            server.stop()
    return "PASS: packaged localhost API, math, physics, Tutor, persistence, port reuse, and CTRL_BREAK shutdown."


def run_existing_instance_behavior(app_root, work_dir):
    port = _free_port()
    server, health = start_server(app_root, port, work_dir, "server-existing-instance.log")
    try:
        env = clean_windows_env(work_dir, app_root)
        code, output = run_short_command(
            [env["COMSPEC"], "/d", "/c", "Start-PHYSIS.cmd", "--port", str(port), "--no-browser", "--offline"],
            app_root, env, work_dir / "logs" / "existing-instance.log", timeout=20)
        if code != 0 or "already running" not in output.lower():
            raise SmokeFailure("A second launch did not identify the existing PHYSIS AI service: " + output[-1200:])
        if not port_accepts_connections(HOST, port, timeout=.5) or health.get("provider") != "mock":
            raise SmokeFailure("The existing server was not left running after the duplicate launch check.")
    finally:
        server.stop()
    if port_accepts_connections(HOST, port, timeout=.4):
        raise SmokeFailure("The existing-instance test did not release its owned localhost port.")
    return "PASS: a same-version offline server is reported as already running and is not terminated by the second launcher."


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--zip", type=Path, help="distribution ZIP to extract, explicitly provision, and smoke")
    source.add_argument("--app", type=Path, help="already-extracted and provisioned PHYSIS-AI app root")
    parser.add_argument("--work-dir", type=Path, help="new or empty scratch directory to preserve extracted app, logs, and data")
    parser.add_argument("--report", type=Path, required=True, help="JSON smoke report destination")
    parser.add_argument("--host-image", choices=("local", "github-hosted", "unknown"), default="unknown",
                        help="label the Windows image used for this run; the harness does not infer cleanliness")
    return parser.parse_args(argv)


def run_report_check(report, name, action, *private_paths):
    item = {"name": name, "status": "RUNNING", "details": ""}
    report["checks"].append(item)
    try:
        details = action()
    except Exception as exc:
        item["status"] = "FAIL"
        item["details"] = sanitize(f"{type(exc).__name__}: {exc}", *private_paths)
        raise
    item["status"] = "PASS"
    item["details"] = sanitize(details, *private_paths)
    return details


def cleanup_active_processes():
    for process, (job, env) in list(ACTIVE_PROCESSES.items()):
        if process.poll() is None:
            try:
                send_console_signal_to_private_console(process, "ctrl_break")
                process.wait(timeout=15)
            except Exception:
                _scoped_force_cleanup(process, job, env)
        if job:
            job.close()
        ACTIVE_PROCESSES.pop(process, None)


def main(argv=None):
    args = parse_args(argv)
    if sys.platform != "win32":
        print("BLOCKED: Windows distribution smoke requires a Windows host.", file=sys.stderr)
        return 2
    work_dir = None
    app_root = None
    report = {"schema_version": 1, "app_version": EXPECTED_APP_VERSION,
              "mode": "zip" if args.zip else "app", "platform": "Windows x64",
              "host_image": args.host_image,
              "provider": "mock",
              "application_network": "PHYSIS_OFFLINE=1; loopback only",
              "setup_network": "only the explicit Setup-Runtime.cmd step may fetch hash-verified sources over HTTPS",
              "staging_path": "Korean and space-containing temporary path (absolute path omitted)",
              "started_utc": utc_now(), "checks": [], "overall": "RUNNING"}
    try:
        work_dir = make_work_dir(args.work_dir)
        if args.zip:
            extracted_parent = work_dir / "한글 경로 space 포함"
            extracted_parent.mkdir(parents=True, exist_ok=False)
            extraction_root = extracted_parent / "PHYSIS AI 0.4.1"
            app_root = extract_zip_safely(args.zip, extraction_root)
            report["app_path_relative_to_work_dir"] = "한글 경로 space 포함/PHYSIS AI 0.4.1/PHYSIS-AI"
            report["checks"].append({"name": "zip_extraction_and_layout", "status": "PASS",
                                     "details": "Archive CRC passed; safe extraction completed under a Korean and space-containing staging path."})
            run_report_check(report, "runtime_absence_simulation",
                             lambda: test_archive_runtime_absence(app_root, work_dir), work_dir, app_root)
            report["checks"].append({"name": "runtime_setup", "status": "RUNNING",
                                     "details": "Explicit user-style Setup-Runtime.cmd invocation."})
            env = clean_windows_env(work_dir, app_root, setup=True)
            code, setup_output = run_short_command(
                [env["COMSPEC"], "/d", "/c", "Setup-Runtime.cmd"], app_root, env,
                work_dir / "logs" / "setup-runtime.log", timeout=900)
            if code != 0 or not (app_root / "runtime" / "python.exe").is_file():
                report["checks"][-1].update(status="FAIL", details="Explicit Setup-Runtime.cmd did not provision runtime/python.exe. "
                                           + _read_log(work_dir / "logs" / "setup-runtime.log", work_dir, app_root)[-1800:])
                raise SmokeFailure("Explicit runtime setup failed or runtime/python.exe was not created.")
            report["checks"][-1].update(status="PASS", details="The separately invoked Setup-Runtime.cmd created runtime/python.exe; launcher did not install it automatically.")
        else:
            app_root = args.app.expanduser().resolve()
            report["app_path_relative_to_work_dir"] = "external supplied --app path omitted"
            report["checks"].append({"name": "zip_extraction_and_layout", "status": "NOT RUN",
                                     "details": "App mode was supplied with an already-extracted directory."})
            report["checks"].append({"name": "runtime_absence_simulation", "status": "NOT RUN",
                                     "details": "App mode leaves the supplied app directory and its runtime untouched."})
            report["checks"].append({"name": "runtime_setup", "status": "NOT RUN",
                                     "details": "App mode requires runtime/python.exe to have been provisioned already."})
            if not all((app_root / name).is_file() for name in ("Start-PHYSIS.cmd", "runtime-lock.json", "Setup-Runtime.cmd")):
                raise SmokeFailure("--app must point to an extracted PHYSIS-AI package root with its root lock and setup entries.")
            if not (app_root / "runtime" / "python.exe").is_file():
                raise SmokeFailure("--app requires an already-provisioned runtime/python.exe.")

        run_report_check(report, "vc_redist_absence_simulation",
                         lambda: test_missing_vc_redist_diagnostic(app_root, work_dir), work_dir, app_root)
        env = clean_windows_env(work_dir, app_root)
        runtime = {}

        def check_runtime():
            runtime.update(verify_runtime(app_root, env, work_dir / "logs" / "native-runtime-check.log"))
            return "Embedded x64 CPython loaded NumPy/SciPy and solved a matrix with PATH restricted to Windows System32; no host Python or Node was used."

        run_report_check(report, "restricted_path_native_runtime",
                         check_runtime,
                         work_dir, app_root)
        report["runtime"] = {key: runtime[key] for key in ("python", "architecture", "bits", "numpy", "scipy")}
        run_report_check(report, "foreign_port_collision",
                         lambda: test_foreign_port_collision(app_root, work_dir), work_dir, app_root)
        run_report_check(report, "existing_instance_behavior",
                         lambda: run_existing_instance_behavior(app_root, work_dir), work_dir, app_root)
        run_report_check(report, "packaged_api_restart",
                         lambda: test_api_and_restart(app_root, work_dir, report), work_dir, app_root)
        report["overall"] = "PASS"
    except (SmokeFailure, OSError, BadZipFile, subprocess.SubprocessError, ValueError, KeyError) as exc:
        report["overall"] = "FAIL"
        report["error"] = sanitize(f"{type(exc).__name__}: {exc}", work_dir, app_root)
        for item in report["checks"]:
            if item.get("status") == "RUNNING":
                item.update(status="FAIL", details=report["error"])
    except KeyboardInterrupt:
        report["overall"] = "INTERRUPTED"
        report["error"] = "Smoke interrupted; only processes launched by this harness are eligible for scoped cleanup."
        for item in report["checks"]:
            if item.get("status") == "RUNNING":
                item.update(status="INTERRUPTED", details=report["error"])
        raise
    finally:
        try:
            cleanup_active_processes()
        except Exception as exc:
            report["overall"] = "FAIL"
            report["cleanup_error"] = sanitize(f"{type(exc).__name__}: {exc}", work_dir, app_root)
        report["finished_utc"] = utc_now()
        report["work_dir_preserved"] = work_dir is not None
        report_path = args.report.expanduser().absolute()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['overall']}: Windows distribution smoke report written.")
    if report["overall"] != "PASS":
        return 1 if report["overall"] == "FAIL" else 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
