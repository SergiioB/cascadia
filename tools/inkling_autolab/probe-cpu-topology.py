"""Read-only Windows CPU-set topology; does not change affinity or power state."""
import ctypes as C
import json
import socket
import struct
import time

k = C.WinDLL('kernel32', use_last_error=True)
query = k.GetSystemCpuSetInformation
query.restype = C.c_int
query.argtypes = [C.c_void_p, C.c_uint32, C.POINTER(C.c_uint32), C.c_void_p, C.c_uint32]
needed = C.c_uint32()
ok = query(None, 0, C.byref(needed), None, 0)
assert not ok and C.get_last_error() == 122
assert 0 < needed.value <= 1024 * 1024
buffer = C.create_string_buffer(needed.value)
if not query(buffer, len(buffer), C.byref(needed), None, 0):
    raise C.WinError(C.get_last_error())
assert needed.value <= len(buffer)
raw, position, cpus, skipped = buffer.raw[:needed.value], 0, [], []
while position < len(raw):
    assert position + 8 <= len(raw)
    size, kind = struct.unpack_from('<II', raw, position)
    assert size >= 8 and position + size <= len(raw)
    if kind == 0:
        assert size >= 32
        data = raw[position:position + size]
        cpus.append(dict(cpu_set_id=struct.unpack_from('<I', data, 8)[0],
                         group=struct.unpack_from('<H', data, 12)[0],
                         logical_processor=data[14], core_index=data[15],
                         last_level_cache_index=data[16], numa_node_index=data[17],
                         efficiency_class=data[18], parked=bool(data[19] & 1),
                         allocated=bool(data[19] & 2), scheduling_class=data[20]))
    else:
        skipped.append(dict(kind=kind, size=size))
    position += size
assert position == len(raw)
assert len({(p['group'], p['logical_processor']) for p in cpus}) == len(cpus)
print(json.dumps(dict(scope='read_only_windows_cpu_set_topology', unix=time.time(),
                      host=socket.gethostname(), processors=cpus, skipped_records=skipped,
                      caveats=['Efficiency class is OS-reported; higher values denote faster, less power-efficient processors.',
                               'Parked/allocated flags are a point-in-time snapshot. No scheduling settings were changed.']), indent=2))
