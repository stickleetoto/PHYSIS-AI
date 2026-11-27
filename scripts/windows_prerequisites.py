"""Windows runtime diagnostics used by the launcher and its distribution smoke test."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path


VC_REDIST_MINIMUM = (14, 51, 36247, 0)
VC_REDIST_MINIMUM_TEXT = "14.51.36247.0"
VC_REDIST_DOWNLOAD_URL = "https://aka.ms/vc14/vc_redist.x64.exe"
VC_REDIST_INFO_URL = "https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist"
_VC_DLLS = ("vcruntime140.dll", "msvcp140.dll")


class _VSFixedFileInfo(ctypes.Structure):
    _fields_ = [(name, wintypes.DWORD) for name in (
        "dwSignature", "dwStrucVersion", "dwFileVersionMS", "dwFileVersionLS",
        "dwProductVersionMS", "dwProductVersionLS", "dwFileFlagsMask", "dwFileFlags",
        "dwFileOS", "dwFileType", "dwFileSubtype", "dwFileDateMS", "dwFileDateLS",
    )]


def _file_version(path: Path):
    if os.name != "nt":
        return None
    try:
        version = ctypes.WinDLL("version", use_last_error=True)
        version.GetFileVersionInfoSizeW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD))
        version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        version.GetFileVersionInfoW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                                ctypes.c_void_p)
        version.GetFileVersionInfoW.restype = wintypes.BOOL
        version.VerQueryValueW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR,
                                           ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT))
        version.VerQueryValueW.restype = wintypes.BOOL
        ignored = wintypes.DWORD()
        size = version.GetFileVersionInfoSizeW(str(path), ctypes.byref(ignored))
        if not size:
            return None
        data = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(path), 0, size, data):
            return None
        value = ctypes.c_void_p()
        length = wintypes.UINT()
        if not version.VerQueryValueW(data, "\\", ctypes.byref(value), ctypes.byref(length)):
            return None
        info = ctypes.cast(value, ctypes.POINTER(_VSFixedFileInfo)).contents
        return (info.dwFileVersionMS >> 16, info.dwFileVersionMS & 0xFFFF,
                info.dwFileVersionLS >> 16, info.dwFileVersionLS & 0xFFFF)
    except (AttributeError, OSError, ValueError):
        return None


def _candidates(name: str, system32: Path, app_local_dirs):
    yield system32 / name
    for folder in app_local_dirs:
        folder = Path(folder)
        yield folder / name
        # Scientific wheels can carry their compatible VC files in private DLL folders.
        for package in ("numpy.libs", "scipy.libs"):
            dll_folder = folder / "Lib" / "site-packages" / package
            yield dll_folder / name
            if name == "msvcp140.dll" and dll_folder.is_dir():
                yield from dll_folder.glob("msvcp140*.dll")


def _supported(path: Path):
    version = _file_version(path)
    return version is not None and version >= VC_REDIST_MINIMUM


def missing_vc_runtime(system32_dir, app_local_dirs=()):
    """Return a manual-install diagnostic when neither x64 source meets the minimum.

    The launcher calls this only after a real native dependency import/load fails.
    App-local DLLs are considered before asking for a machine-wide installation.
    """
    system32 = Path(system32_dir)
    missing = [name for name in _VC_DLLS
               if not any(_supported(path) for path in _candidates(name, system32, app_local_dirs))]
    if not missing:
        return None
    names = ", ".join(missing)
    return ("The required x64 Microsoft Visual C++ v14 runtime was not found or is older "
            f"than {VC_REDIST_MINIMUM_TEXT} ({names}). Install it manually from "
            f"{VC_REDIST_DOWNLOAD_URL} . Official details: {VC_REDIST_INFO_URL}. "
            "PHYSIS AI does not install it or request administrator access.")


def system32_directory():
    root = Path(os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows")
    return root / "System32"
