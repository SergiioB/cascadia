//! Bounded scratch storage for the optional bulk-read decode path.
//!
//! This caches destination allocations, never expert contents. A lease owns its
//! buffers while Rayon reads and computes; no pool lock covers I/O or compute.
//! The idle pool is shared across layers and capped at 256 MiB per process.
use std::io::{self, Read};
use std::path::Path;
use std::sync::Mutex;

const MAX_IDLE_BYTES: usize = 256 * 1024 * 1024;
static POOL: Mutex<Vec<Vec<u8>>> = Mutex::new(Vec::new());

pub(super) struct ReadBuffers {
    pub buffers: Vec<Vec<u8>>,
}

impl ReadBuffers {
    pub fn acquire(count: usize) -> Self {
        let mut buffers = std::mem::take(&mut *POOL.lock().unwrap_or_else(|e| e.into_inner()));
        buffers.resize_with(count, Vec::new);
        Self { buffers }
    }
}

impl Drop for ReadBuffers {
    fn drop(&mut self) {
        let mut pool = POOL.lock().unwrap_or_else(|e| e.into_inner());
        let mut bytes: usize = pool.iter().map(Vec::capacity).sum();
        for buffer in self.buffers.drain(..) {
            let capacity = buffer.capacity();
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
        first.buffers[0].resize(4096, 17);
        first.buffers[0].fill(17);
        let mut second = ReadBuffers::acquire(2);
        second.buffers[0].resize(4096, 93);
        second.buffers[0].fill(93);
        assert_eq!(first.buffers[0], [17; 4096]);
        assert_ne!(first.buffers[0].as_ptr(), second.buffers[0].as_ptr());
        drop(first);
        assert_eq!(second.buffers[0], [93; 4096]);
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
