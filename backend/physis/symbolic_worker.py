"""One request per process, bounded before loading the symbolic library."""
import json
import os
from pathlib import Path
import sys


def limit_memory():
    size = 512*1024*1024
    if os.name != "nt":
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(size,size))
        return None
    import ctypes as c
    from ctypes import wintypes as w

    class Basic(c.Structure):
        _fields_ = [("process_time",c.c_int64),("job_time",c.c_int64),("flags",w.DWORD),
                    ("min_ws",c.c_size_t),("max_ws",c.c_size_t),("active",w.DWORD),
                    ("affinity",c.c_size_t),("priority",w.DWORD),("scheduling",w.DWORD)]

    class Extended(c.Structure):
        _fields_ = [("basic",Basic),("io",c.c_uint64*6),("process_memory",c.c_size_t),
                    ("job_memory",c.c_size_t),("peak_process",c.c_size_t),("peak_job",c.c_size_t)]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = (c.c_void_p,w.LPCWSTR)
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = (w.HANDLE,c.c_int,c.c_void_p,w.DWORD)
    kernel.AssignProcessToJobObject.argtypes = (w.HANDLE,w.HANDLE)
    kernel.GetCurrentProcess.restype = w.HANDLE
    job = kernel.CreateJobObjectW(None,None)
    info = Extended()
    info.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.process_memory = size
    if not (job and kernel.SetInformationJobObject(job,9,c.byref(info),c.sizeof(info))
            and kernel.AssignProcessToJobObject(job,kernel.GetCurrentProcess())):
        raise OSError("Could not constrain the symbolic worker.")
    return job  # keep the job open through worker exit


def main():
    try:
        job = limit_memory()
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        data = json.loads(sys.stdin.buffer.read(16_384))
        if "numeric" in data:
            from physis.math_numerics import calculate
            args = data["numeric"]
        elif "matrix" in data:
            from physis.math_matrices import matrices as calculate
            args = data["matrix"]
        elif "laboratory" in data:
            from physis.math_lab_engine import calculate_lab as calculate
            args = data["laboratory"]
        else:
            from physis.symbolic_core import calculate
            args = data
        if "--notify-ready" in sys.argv:
            sys.stdout.buffer.write(b"READY\n")
            sys.stdout.buffer.flush()
        result = calculate(args)
    except (MemoryError,OSError):
        result = {"status":"unverifiable","detail":"메모리 제한 안에서 계산할 수 없습니다."}
    except Exception:
        result = {"status":"unverifiable","detail":"제한된 계산 환경에서 결과를 확정할 수 없습니다."}
    sys.stdout.buffer.write(json.dumps(result,allow_nan=False).encode("ascii"))


if __name__ == "__main__":
    main()
