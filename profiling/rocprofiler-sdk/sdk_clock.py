"""Use the installed SDK's actual timestamp API, never an inferred offset."""
import ctypes
import hashlib
from pathlib import Path
import time

SDK_PATH=Path('/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/librocprofiler-sdk.so.1')
SDK_SHA256='9280eae676a8d3d135096a327a2524b2b50a9146b13d850c626e0d8e0e49b7b8'
CLOCK_NAME='CLOCK_BOOTTIME'
_fn=None
_lib=None

def stamp():
    global _fn, _lib
    if _fn is None:
        if SDK_PATH.is_symlink() or hashlib.sha256(SDK_PATH.read_bytes()).hexdigest()!=SDK_SHA256:
            raise ValueError('SDK timestamp library identity mismatch')
        _lib=ctypes.CDLL(str(SDK_PATH))
        _fn=_lib.rocprofiler_get_timestamp
        _fn.argtypes=[ctypes.POINTER(ctypes.c_uint64)]
        _fn.restype=ctypes.c_int
    before=time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    value=ctypes.c_uint64()
    status=_fn(ctypes.byref(value))
    after=time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    if status!=0 or not before<=value.value<=after:
        raise ValueError('SDK timestamp does not match the proven BOOTTIME domain')
    return value.value
