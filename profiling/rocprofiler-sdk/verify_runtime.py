"""No-device installed SDK and clock identity check."""
import hashlib
import json
from pathlib import Path
import sdk_clock

root = Path(__file__).resolve().parent
manifest = json.loads((root / "rocprofiler-sdk-repair.json").read_text())
for rel, expected in manifest["runtime_files"].items():
    path = root / Path(rel).name
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("installed helper identity mismatch: " + path.name)
for path in [sdk_clock.SDK_PATH, Path("/opt/rocm/core-10.0/lib/librocprofiler-sdk.so.1.3.5")]:
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sdk_sha256"]:
        raise ValueError("installed SDK identity mismatch: " + str(path))
start = sdk_clock.stamp()
end = sdk_clock.stamp()
if not 0 < start <= end:
    raise ValueError("nonmonotonic SDK clock")
print(json.dumps({"status": "PASS", "scope": "no-device SDK/clock verification", "sdk_sha256": manifest["sdk_sha256"], "clock": sdk_clock.CLOCK_NAME, "timestamp_ns": end}))
