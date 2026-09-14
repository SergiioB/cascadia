"""Read-only allocation metadata for model experts after component084 exits."""
import ctypes as C
import importlib.util
import json
import os
from pathlib import Path
import statistics
import struct
import time

ROOT = Path('C:/Users/devcloud/inkling-autolab')
spec = importlib.util.spec_from_file_location('read_probe', Path(__file__).with_name('uncached-read-probe.py'))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def status(value, **fields):
    path = ROOT / 'file-extents-probe-state.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(status=value, pid=os.getpid(), unix=time.time(), **fields), indent=2))
    temporary.replace(path)


def main():
    out = ROOT / '086-file-extents.json'
    assert not out.exists()
    deadline = time.monotonic() + 7200
    while True:
        state_path = ROOT / 'compressed-read-probe-state.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if state.get('status') in ('complete', 'failed') and not base.psutil.pid_exists(state['pid']) and not base.active_full(ROOT):
            break
        if time.monotonic() >= deadline:
            raise TimeoutError('Waiting for component084')
        time.sleep(15)
    import msvcrt
    with (ROOT / 'baseline-queue.lock').open('a+b') as slot:
        slot.seek(0)
        msvcrt.locking(slot.fileno(), msvcrt.LK_NBLCK, 1)
        assert not base.active_full(ROOT)
        status('querying')
        native = base.NativeIO()
        k = native.k
        k.DeviceIoControl.restype = C.c_int
        k.DeviceIoControl.argtypes = [C.c_void_p, C.c_uint32, C.c_void_p, C.c_uint32,
                                     C.c_void_p, C.c_uint32, C.POINTER(C.c_uint32), C.c_void_p]
        k.GetDiskFreeSpaceW.restype = C.c_int
        k.GetDiskFreeSpaceW.argtypes = [C.c_wchar_p] + [C.POINTER(C.c_uint32)] * 4
        sectors, sector_bytes, free, total = (C.c_uint32() for _ in range(4))
        if not k.GetDiskFreeSpaceW('C:\\', C.byref(sectors), C.byref(sector_bytes), C.byref(free), C.byref(total)):
            raise C.WinError(C.get_last_error())
        cluster_bytes = sectors.value * sector_bytes.value
        assert cluster_bytes > 0
        records = []
        for layer in (2, 14, 27, 40, 53, 65):
            for expert in (0, 43, 85, 128, 170, 213):
                path = ROOT / f'model/experts/layer_{layer:02}/expert_{expert:03}.bin'
                size = path.stat().st_size
                # One extent per allocated cluster would still fit this bounded
                # buffer. The query accesses allocation metadata, not file data.
                clusters = (size + cluster_bytes - 1) // cluster_bytes
                assert 0 < clusters <= 65536
                buffer = C.create_string_buffer(16 + 16 * clusters)
                start, returned = C.c_int64(0), C.c_uint32()
                with native.handle(path) as handle:
                    # CTL_CODE(FILE_DEVICE_FILE_SYSTEM,28,METHOD_NEITHER,FILE_ANY_ACCESS)
                    code = (9 << 16) | (28 << 2) | 3
                    if not k.DeviceIoControl(handle, code, C.byref(start), C.sizeof(start),
                                             buffer, len(buffer), C.byref(returned), None):
                        raise C.WinError(C.get_last_error())
                assert 16 <= returned.value <= len(buffer)
                raw = buffer.raw[:returned.value]
                count = struct.unpack_from('<I', raw, 0)[0]
                current = struct.unpack_from('<q', raw, 8)[0]
                assert current == 0 and 0 < count <= (len(raw) - 16) // 16
                extents = []
                for index in range(count):
                    following, lcn = struct.unpack_from('<qq', raw, 16 + 16 * index)
                    assert following > current and lcn >= -1
                    extents.append(dict(clusters=following - current, lcn=lcn))
                    current = following
                assert current == clusters
                runs, previous_end = 0, None
                for extent in extents:
                    if extent['lcn'] < 0:
                        previous_end = None
                    else:
                        if extent['lcn'] != previous_end:
                            runs += 1
                        previous_end = extent['lcn'] + extent['clusters']
                records.append(dict(path=str(path.relative_to(ROOT)), bytes=size, extents=extents,
                                    extent_count=count, physical_runs=runs,
                                    unallocated_or_compressed_clusters=sum(e['clusters'] for e in extents if e['lcn'] == -1)))
        report = dict(scope='read_only_original_expert_allocation_metadata', cluster_bytes=cluster_bytes,
                      samples=records, files=len(records),
                      files_with_multiple_physical_runs=sum(r['physical_runs'] > 1 for r in records),
                      median_physical_runs=statistics.median(r['physical_runs'] for r in records),
                      maximum_physical_runs=max(r['physical_runs'] for r in records),
                      caveats=['36 fixed original experts across six layers, not every model file.',
                               'Allocation metadata is not a throughput measurement.',
                               'No file data, allocation or volume settings were changed.'])
        with out.open('x') as f:
            json.dump(report, f, indent=2)
        print(json.dumps({k: v for k, v in report.items() if k != 'samples'}))


if __name__ == '__main__':
    import msvcrt
    with (ROOT / 'file-extents-probe.lock').open('a+b') as owner:
        owner.seek(0)
        msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            status('waiting_for_084')
            main()
            status('complete')
        except BaseException as error:
            status('failed', error=str(error))
            raise
