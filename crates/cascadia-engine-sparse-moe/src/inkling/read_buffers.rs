//! Bounded scratch storage for the optional bulk-read decode path.
//!
//! This caches destination allocations, never expert contents. A lease owns its
//! buffers while Rayon reads and computes; no pool lock covers I/O or compute.
//! The idle pool is shared across layers and capped at 256 MiB per process.
use std::io::{self, Read};
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};

const MAX_IDLE_BYTES: usize = 256 * 1024 * 1024;
static POOL: Mutex<Vec<ReadBuffer>> = Mutex::new(Vec::new());
static UNCACHED_BYTES: AtomicU64 = AtomicU64::new(0);
static UNCACHED_FALLBACKS: AtomicU64 = AtomicU64::new(0);
#[cfg(any(windows, test))]
const IO_ALIGNMENT: usize = 4096;

/// Process-wide completed uncached read bytes and fallback attempts. These
/// diagnose the optional Windows decode path, not physical disk traffic.
pub fn uncached_read_statistics() -> (u64, u64) {
    (
        UNCACHED_BYTES.load(Ordering::Relaxed),
        UNCACHED_FALLBACKS.load(Ordering::Relaxed),
    )
}

#[derive(Default)]
pub(super) struct ReadBuffer {
    bytes: Vec<u8>,
    offset: usize,
    length: usize,
}

#[derive(Debug, PartialEq)]
enum ReadMode {
    Cached,
    Uncached,
    Fallback,
}

impl ReadBuffer {
    pub(super) fn allocated_bytes(&self) -> usize {
        self.bytes.capacity()
    }

    pub fn as_slice(&self) -> &[u8] {
        &self.bytes[self.offset..self.offset + self.length]
    }

    // Reserve padding inside an ordinary Vec, then take an aligned subslice.
    // No unsafe allocation, physical page locking or custom deallocator.
    #[cfg(any(windows, test))]
    fn prepare_aligned(&mut self, expected: usize) -> io::Result<()> {
        let allocation = expected.checked_add(IO_ALIGNMENT - 1).ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidInput, "expert allocation overflow")
        })?;
        self.bytes.resize(allocation, 0);
        self.offset = self.bytes.as_ptr().align_offset(IO_ALIGNMENT);
        self.length = 0;
        Ok(())
    }

    fn read_mode(&mut self, path: &Path, expected: usize, uncached: bool) -> io::Result<ReadMode> {
        self.offset = 0;
        self.length = 0;
        if uncached && self.read_uncached(path, expected).is_ok() {
            self.length = expected;
            return Ok(ReadMode::Uncached);
        }
        // Unsupported lengths/platforms/filesystems or failed direct reads
        // retry a complete cached read; partial/stale bytes cannot be consumed.
        self.offset = 0;
        read_into(path, expected, &mut self.bytes)?;
        self.length = expected;
        Ok(if uncached {
            ReadMode::Fallback
        } else {
            ReadMode::Cached
        })
    }

    #[cfg(windows)]
    fn read_uncached(&mut self, path: &Path, expected: usize) -> io::Result<()> {
        use std::os::windows::fs::OpenOptionsExt;
        // PTL has 512-byte logical / 4096-byte physical sectors. Larger or
        // unsupported alignment requirements are handled by the cached retry.
        // https://learn.microsoft.com/en-us/windows/win32/fileio/file-buffering
        if expected == 0 || expected % IO_ALIGNMENT != 0 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "unaligned expert length",
            ));
        }
        let mut file = std::fs::OpenOptions::new()
            .read(true)
            .custom_flags(0x20000000) // FILE_FLAG_NO_BUFFERING; read access only.
            .open(path)?;
        if file.metadata()?.len() != expected as u64 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "expert size changed",
            ));
        }
        self.prepare_aligned(expected)?;
        file.read_exact(&mut self.bytes[self.offset..self.offset + expected])?;
        // An extra one-byte EOF read would violate the sector-size contract.
        // As with mmap execution, weights must remain immutable while loaded.
        if file.metadata()?.len() != expected as u64 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "expert size changed during read",
            ));
        }
        Ok(())
    }

    #[cfg(not(windows))]
    fn read_uncached(&mut self, _path: &Path, _expected: usize) -> io::Result<()> {
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "uncached Inkling reads require Windows",
        ))
    }

    pub fn read(&mut self, path: &Path, expected: usize) -> io::Result<()> {
        static ENABLED: OnceLock<bool> = OnceLock::new();
        let enabled = *ENABLED
            .get_or_init(|| cfg!(windows) && super::env_flag("CASCADIA_INKLING_UNCACHED_READS"));
        let result = self.read_mode(path, expected, enabled);
        match &result {
            Ok(ReadMode::Uncached) => {
                UNCACHED_BYTES.fetch_add(expected as u64, Ordering::Relaxed);
            }
            Ok(ReadMode::Fallback) | Err(_) if enabled => {
                UNCACHED_FALLBACKS.fetch_add(1, Ordering::Relaxed);
            }
            _ => {}
        }
        result.map(|_| ())
    }
}

pub(super) struct ReadBuffers {
    pub buffers: Vec<ReadBuffer>,
}

impl ReadBuffers {
    pub fn acquire(count: usize) -> Self {
        let mut buffers = std::mem::take(&mut *POOL.lock().unwrap_or_else(|e| e.into_inner()));
        buffers.resize_with(count, ReadBuffer::default);
        Self { buffers }
    }
}

impl Drop for ReadBuffers {
    fn drop(&mut self) {
        let mut pool = POOL.lock().unwrap_or_else(|e| e.into_inner());
        let mut bytes: usize = pool.iter().map(|b| b.bytes.capacity()).sum();
        for buffer in self.buffers.drain(..) {
            let capacity = buffer.bytes.capacity();
            if capacity > 0 && capacity <= MAX_IDLE_BYTES - bytes {
                bytes += capacity;
                pool.push(buffer);
            }
        }
    }
}

/// Overwrite all expected bytes before exposing a reusable buffer to a kernel.
/// Model files must remain immutable for the lifetime of their mappings.
pub(super) fn read_into(path: &Path, expected: usize, buffer: &mut Vec<u8>) -> io::Result<()> {
    let mut file = std::fs::File::open(path)?;
    if file.metadata()?.len() != expected as u64 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "expert size changed",
        ));
    }
    buffer.resize(expected, 0);
    file.read_exact(buffer)?;
    let mut extra = [0];
    if file.read(&mut extra)? != 0 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "expert grew during read",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn overwrites_previous_expert_without_reallocating() {
        let mut first = tempfile::NamedTempFile::new().unwrap();
        let mut second = tempfile::NamedTempFile::new().unwrap();
        first.write_all(&[17; 4096]).unwrap();
        second.write_all(&[93; 4096]).unwrap();
        let mut bytes = vec![0; 4096];
        let ptr = bytes.as_ptr();
        read_into(first.path(), 4096, &mut bytes).unwrap();
        assert_eq!(bytes, [17; 4096]);
        read_into(second.path(), 4096, &mut bytes).unwrap();
        assert_eq!(bytes, [93; 4096]);
        assert_eq!(ptr, bytes.as_ptr());
    }

    #[test]
    fn rejects_missing_short_and_oversized_experts() {
        let mut file = tempfile::NamedTempFile::new().unwrap();
        file.write_all(&[17; 32]).unwrap();
        let mut bytes = vec![93; 64];
        assert!(read_into(file.path(), 64, &mut bytes).is_err());
        assert!(read_into(file.path(), 16, &mut bytes).is_err());
        assert!(read_into(&file.path().join("missing"), 32, &mut bytes).is_err());
    }

    #[test]
    fn overlapping_leases_own_disjoint_buffers() {
        let mut first = ReadBuffers::acquire(2);
        first.buffers[0].bytes.resize(4096, 17);
        first.buffers[0].bytes.fill(17);
        let mut second = ReadBuffers::acquire(2);
        second.buffers[0].bytes.resize(4096, 93);
        second.buffers[0].bytes.fill(93);
        assert_eq!(first.buffers[0].bytes, [17; 4096]);
        assert_ne!(
            first.buffers[0].bytes.as_ptr(),
            second.buffers[0].bytes.as_ptr()
        );
        drop(first);
        assert_eq!(second.buffers[0].bytes, [93; 4096]);
    }

    #[test]
    fn alignment_survives_resizing_and_reuse() {
        let mut buffer = ReadBuffer::default();
        for length in [4096, 31850496, 8192, 31850496] {
            buffer.prepare_aligned(length).unwrap();
            buffer.length = length;
            assert_eq!(buffer.as_slice().as_ptr().align_offset(IO_ALIGNMENT), 0);
            assert_eq!(buffer.as_slice().len(), length);
        }
        assert!(buffer.prepare_aligned(usize::MAX).is_err());
    }

    #[test]
    fn incompatible_length_falls_back_and_failed_read_exposes_no_bytes() {
        let mut file = tempfile::NamedTempFile::new().unwrap();
        file.write_all(&[17; 32]).unwrap();
        let mut buffer = ReadBuffer::default();
        assert_eq!(
            buffer.read_mode(file.path(), 32, true).unwrap(),
            ReadMode::Fallback
        );
        assert_eq!(buffer.as_slice(), [17; 32]);
        assert!(buffer.read_mode(file.path(), 64, true).is_err());
        assert!(buffer.as_slice().is_empty());
        assert!(buffer
            .read_mode(&file.path().join("missing"), 32, true)
            .is_err());
        assert!(buffer.as_slice().is_empty());
    }

    #[cfg(windows)]
    #[test]
    fn native_uncached_read_overwrites_aligned_bytes_and_reuses_allocation() {
        let mut first = tempfile::NamedTempFile::new().unwrap();
        let mut second = tempfile::NamedTempFile::new().unwrap();
        first.write_all(&[17; 65536]).unwrap();
        second.write_all(&[93; 65536]).unwrap();
        first.as_file().sync_all().unwrap();
        second.as_file().sync_all().unwrap();
        let mut buffer = ReadBuffer::default();
        assert_eq!(
            buffer.read_mode(first.path(), 65536, true).unwrap(),
            ReadMode::Uncached
        );
        assert_eq!(buffer.as_slice(), [17; 65536]);
        let pointer = buffer.as_slice().as_ptr();
        assert_eq!(
            buffer.read_mode(second.path(), 65536, true).unwrap(),
            ReadMode::Uncached
        );
        assert_eq!(buffer.as_slice(), [93; 65536]);
        assert_eq!(buffer.as_slice().as_ptr(), pointer);
    }

    #[cfg(windows)]
    #[test]
    fn native_aligned_int4_canary_preserves_mapped_kernel_bits() {
        use crate::dsv4::expert_mmap::MmapExpert;
        let source = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/inkling_export/experts/layer_01");
        let mut buffer = ReadBuffer::default();
        let x: Vec<f32> = (0..64).map(|i| (i as f32 - 7.0) * 0.03125).collect();
        for name in ["expert_000.bin", "expert_001.bin"] {
            // MmapExpert allows trailing bytes. Pad only this disposable tiny
            // canary so its real matrices exercise the uncached aligned path.
            let mut bytes = std::fs::read(source.join(name)).unwrap();
            bytes.resize(bytes.len().div_ceil(IO_ALIGNMENT) * IO_ALIGNMENT, 0);
            let mut file = tempfile::NamedTempFile::new().unwrap();
            file.write_all(&bytes).unwrap();
            file.as_file().sync_all().unwrap();
            let expert = MmapExpert::open(file.path(), 64, 32).unwrap();
            assert_eq!(
                buffer.read_mode(file.path(), bytes.len(), true).unwrap(),
                ReadMode::Uncached
            );
            assert_eq!(buffer.as_slice(), bytes);
            let expected = crate::glm::ffn::swiglu_mmap(&expert, &x);
            let got = expert.swiglu_from(buffer.as_slice(), &x);
            assert_eq!(
                got.iter().map(|x| x.to_bits()).collect::<Vec<_>>(),
                expected.iter().map(|x| x.to_bits()).collect::<Vec<_>>()
            );
        }
    }

    #[test]
    fn reusable_real_int4_bytes_match_mapped_kernel_after_expert_changes() {
        use crate::dsv4::expert_mmap::MmapExpert;
        let dir = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/inkling_export/experts/layer_01");
        // The committed fixture has hidden64 and expert intermediate32.
        let paths = [dir.join("expert_000.bin"), dir.join("expert_001.bin")];
        let mut buffer = Vec::new();
        let x: Vec<f32> = (0..64).map(|i| (i as f32 - 7.0) * 0.03125).collect();
        for path in paths.iter().cycle().take(4) {
            let expert = MmapExpert::open(path, 64, 32).unwrap();
            read_into(path, expert.bin_len(), &mut buffer).unwrap();
            assert_eq!(buffer, expert.read_bytes().unwrap());
            let expected = crate::glm::ffn::swiglu_mmap(&expert, &x);
            let got = expert.swiglu_from(&buffer, &x);
            assert_eq!(
                got.iter().map(|x| x.to_bits()).collect::<Vec<_>>(),
                expected.iter().map(|x| x.to_bits()).collect::<Vec<_>>()
            );
        }
    }
}
