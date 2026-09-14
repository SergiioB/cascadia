"""Read-only Win32 allocation queries used by the storage-layout component."""
import ctypes as C
import struct


def parse(raw, logical_clusters):
    assert len(raw) >= 16
    count = struct.unpack_from('<I', raw, 0)[0]
    current = struct.unpack_from('<q', raw, 8)[0]
    assert current == 0 and 0 < count <= (len(raw) - 16) // 16
    extents = []
    for index in range(count):
        following, lcn = struct.unpack_from('<qq', raw, 16 + 16 * index)
        assert following > current and lcn >= -1
        extents.append(dict(clusters=following - current, lcn=lcn))
        current = following
    assert current == logical_clusters
    runs, previous_end = 0, None
    for extent in extents:
        if extent['lcn'] < 0:
            previous_end = None
        else:
            if extent['lcn'] != previous_end:
                runs += 1
            previous_end = extent['lcn'] + extent['clusters']
    return dict(extents=extents, extent_count=count, physical_runs=runs,
                unallocated_or_compressed_clusters=sum(e['clusters'] for e in extents if e['lcn'] == -1))


class ExtentQuery:
    def __init__(self, native):
        self.native = native
        k = native.k
        k.DeviceIoControl.restype = C.c_int
        k.DeviceIoControl.argtypes = [C.c_void_p, C.c_uint32, C.c_void_p, C.c_uint32,
                                     C.c_void_p, C.c_uint32, C.POINTER(C.c_uint32), C.c_void_p]
        k.GetDiskFreeSpaceW.restype = C.c_int
        k.GetDiskFreeSpaceW.argtypes = [C.c_wchar_p] + [C.POINTER(C.c_uint32)] * 4
        sectors, sector_bytes, free, total = (C.c_uint32() for _ in range(4))
        if not k.GetDiskFreeSpaceW('C:\\', C.byref(sectors), C.byref(sector_bytes), C.byref(free), C.byref(total)):
            raise C.WinError(C.get_last_error())
        self.cluster_bytes = sectors.value * sector_bytes.value
        assert self.cluster_bytes > 0

    def query(self, path):
        size = path.stat().st_size
        clusters = (size + self.cluster_bytes - 1) // self.cluster_bytes
        assert 0 < clusters <= 65536
        buffer = C.create_string_buffer(16 + 16 * clusters)
        start, returned = C.c_int64(0), C.c_uint32()
        with self.native.handle(path) as handle:
            code = (9 << 16) | (28 << 2) | 3  # FSCTL_GET_RETRIEVAL_POINTERS
            if not self.native.k.DeviceIoControl(handle, code, C.byref(start), C.sizeof(start),
                                                 buffer, len(buffer), C.byref(returned), None):
                raise C.WinError(C.get_last_error())
        assert 16 <= returned.value <= len(buffer)
        return dict(bytes=size, **parse(buffer.raw[:returned.value], clusters))
