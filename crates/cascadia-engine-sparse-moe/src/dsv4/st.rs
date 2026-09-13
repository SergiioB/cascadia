//! Minimal safetensors reader for dsv4 shells and test fixtures.
//!
//! Unlike `cascadia_int4_gemm::safetensors_source::Shard` (mmap'd, expert-
//! oriented, K2.6-shaped accessors), this is a small generic name -> tensor
//! reader: header parse and dtype-aware decode to f32/i32. Whole-file owned
//! storage is the default; opt-in read-only mappings support sparse BF16
//! embedding lookups without copying multi-GiB payloads.
//! Shell files are a few hundred MB at most; fixtures are kilobytes.

use std::collections::HashMap;
use std::path::Path;
use std::sync::Arc;

use half::bf16;
use memmap2::Mmap;

#[derive(Debug, thiserror::Error)]
pub enum StError {
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
    #[error("bad safetensors header: {0}")]
    Header(String),
    #[error("tensor not found: {0}")]
    NotFound(String),
    #[error("dtype {0} unsupported for {1}")]
    Dtype(String, String),
}

#[derive(Debug, Clone)]
pub struct TensorInfo {
    pub dtype: String,
    pub shape: Vec<usize>,
    start: usize,
    end: usize,
}

enum Storage {
    Owned(Vec<u8>),
    Mapped(Arc<Mmap>),
}

impl std::ops::Deref for Storage {
    type Target = [u8];

    fn deref(&self) -> &[u8] {
        match self {
            Self::Owned(data) => data,
            Self::Mapped(data) => data,
        }
    }
}

/// A validated, aligned BF16 tensor view which keeps its file mapping alive.
/// The model file must remain immutable for the lifetime of this view.
pub struct MappedBf16 {
    data: Arc<Mmap>,
    start: usize,
    len: usize,
}

impl MappedBf16 {
    pub fn as_slice(&self) -> &[u16] {
        // SAFETY: mapped_bf16 checks the byte range, u16 alignment, even
        // payload size and native little endian. The Arc owns the immutable
        // mapping for the entire borrowed slice's lifetime; u16 has no invalid
        // bit patterns. Export files must not be modified while loaded.
        unsafe { std::slice::from_raw_parts(self.data.as_ptr().add(self.start).cast(), self.len) }
    }
}

/// Safetensors header and owned bytes, or an opt-in read-only mapping.
pub struct StFile {
    data: Storage,
    data_start: usize,
    pub tensors: HashMap<String, TensorInfo>,
}

impl StFile {
    pub fn open(path: &Path) -> Result<Self, StError> {
        Self::from_storage(Storage::Owned(std::fs::read(path)?))
    }

    /// Map a model file without reading/copying its entire payload. The file
    /// must remain immutable while this reader or any tensor view is alive.
    pub fn open_mmap(path: &Path) -> Result<Self, StError> {
        let file = std::fs::File::open(path)?;
        // SAFETY: same immutable-model-file contract as MmapExpert::open.
        let data = unsafe { Mmap::map(&file)? };
        Self::from_storage(Storage::Mapped(Arc::new(data)))
    }

    fn from_storage(data: Storage) -> Result<Self, StError> {
        if data.len() < 8 {
            return Err(StError::Header("file shorter than header length".into()));
        }
        let mut hdr = [0u8; 8];
        hdr.copy_from_slice(&data[..8]);
        let hlen = usize::try_from(u64::from_le_bytes(hdr))
            .map_err(|_| StError::Header("header length exceeds address space".into()))?;
        if hlen > data.len() - 8 {
            return Err(StError::Header("header length exceeds file".into()));
        }
        let json: serde_json::Value = serde_json::from_slice(&data[8..8 + hlen])
            .map_err(|e| StError::Header(e.to_string()))?;
        let obj = json
            .as_object()
            .ok_or_else(|| StError::Header("header not a json object".into()))?;
        let mut tensors = HashMap::with_capacity(obj.len());
        for (k, v) in obj {
            if k == "__metadata__" {
                continue;
            }
            let dtype = v
                .get("dtype")
                .and_then(|d| d.as_str())
                .ok_or_else(|| StError::Header(format!("{k}: missing dtype")))?
                .to_string();
            let shape: Vec<usize> = v
                .get("shape")
                .and_then(|s| s.as_array())
                .ok_or_else(|| StError::Header(format!("{k}: missing shape")))?
                .iter()
                .map(|x| {
                    x.as_u64()
                        .and_then(|n| usize::try_from(n).ok())
                        .ok_or_else(|| StError::Header(format!("{k}: invalid shape")))
                })
                .collect::<Result<_, _>>()?;
            let off = v
                .get("data_offsets")
                .and_then(|o| o.as_array())
                .ok_or_else(|| StError::Header(format!("{k}: missing data_offsets")))?;
            if off.len() != 2 {
                return Err(StError::Header(format!("{k}: expected two data offsets")));
            }
            let offset = |value: &serde_json::Value| {
                value
                    .as_u64()
                    .and_then(|n| usize::try_from(n).ok())
                    .ok_or_else(|| StError::Header(format!("{k}: invalid data offset")))
            };
            let start = offset(&off[0])?;
            let end = offset(&off[1])?;
            if start > end || end > data.len() - (8 + hlen) {
                return Err(StError::Header(format!("{k}: data offsets exceed payload")));
            }
            tensors.insert(
                k.clone(),
                TensorInfo {
                    dtype,
                    shape,
                    start,
                    end,
                },
            );
        }
        Ok(Self {
            data,
            data_start: 8 + hlen,
            tensors,
        })
    }

    pub fn info(&self, name: &str) -> Result<&TensorInfo, StError> {
        self.tensors
            .get(name)
            .ok_or_else(|| StError::NotFound(name.into()))
    }

    /// Borrow native BF16 bits without copying. Non-BF16, owned, unaligned or
    /// non-little-endian storage returns None so callers can use bf16_bits.
    /// Malformed BF16 shape/payload metadata is an error, never an unsafe view.
    pub fn mapped_bf16(&self, name: &str) -> Result<Option<MappedBf16>, StError> {
        let (ti, bytes) = self.bytes(name)?;
        if ti.dtype != "BF16" {
            return Ok(None);
        }
        let elements = ti.shape.iter().try_fold(1usize, |n, &d| n.checked_mul(d));
        if elements.and_then(|n| n.checked_mul(2)) != Some(bytes.len()) {
            return Err(StError::Header(format!(
                "{name}: BF16 shape/payload mismatch"
            )));
        }
        let Storage::Mapped(data) = &self.data else {
            return Ok(None);
        };
        let start = self.data_start + ti.start;
        if !cfg!(target_endian = "little")
            || !(bytes.as_ptr() as usize).is_multiple_of(std::mem::align_of::<u16>())
        {
            return Ok(None);
        }
        Ok(Some(MappedBf16 {
            data: Arc::clone(data),
            start,
            len: (ti.end - ti.start) / 2,
        }))
    }

    fn bytes(&self, name: &str) -> Result<(&TensorInfo, &[u8]), StError> {
        let ti = self.info(name)?;
        let invalid = || StError::Header(format!("{name}: invalid payload range"));
        let start = self.data_start.checked_add(ti.start).ok_or_else(invalid)?;
        let end = self.data_start.checked_add(ti.end).ok_or_else(invalid)?;
        Ok((ti, self.data.get(start..end).ok_or_else(invalid)?))
    }

    /// Decode to f32 (accepts F32, BF16, F16).
    pub fn f32(&self, name: &str) -> Result<(Vec<usize>, Vec<f32>), StError> {
        let (ti, b) = self.bytes(name)?;
        let out = match ti.dtype.as_str() {
            "F32" => b
                .chunks_exact(4)
                .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
                .collect(),
            "BF16" => b
                .chunks_exact(2)
                .map(|c| bf16::from_le_bytes([c[0], c[1]]).to_f32())
                .collect(),
            "F16" => b
                .chunks_exact(2)
                .map(|c| half::f16::from_le_bytes([c[0], c[1]]).to_f32())
                .collect(),
            other => return Err(StError::Dtype(other.into(), name.into())),
        };
        Ok((ti.shape.clone(), out))
    }

    /// The tensor as bf16 bits (accepts BF16, F32, F16). A BF16 tensor is a
    /// straight copy of its little-endian payload — no widen-to-f32 pass and
    /// no f32 transient, which matters for multi-GiB bf16 tables (the Inkling
    /// embed / unembed and every attention projection). F32 / F16 are
    /// narrowed with round-to-nearest-even, exactly `bf16::from_f32(f32(x))`,
    /// so the result equals [`Self::f32`] narrowed element by element for
    /// every dtype.
    pub fn bf16_bits(&self, name: &str) -> Result<(Vec<usize>, Vec<u16>), StError> {
        let (ti, b) = self.bytes(name)?;
        let out: Vec<u16> = match ti.dtype.as_str() {
            "BF16" => {
                let mut out = vec![0u16; b.len() / 2];
                for (o, c) in out.iter_mut().zip(b.chunks_exact(2)) {
                    *o = u16::from_le_bytes([c[0], c[1]]);
                }
                out
            }
            "F32" => b
                .chunks_exact(4)
                .map(|c| bf16::from_f32(f32::from_le_bytes([c[0], c[1], c[2], c[3]])).to_bits())
                .collect(),
            "F16" => b
                .chunks_exact(2)
                .map(|c| bf16::from_f32(half::f16::from_le_bytes([c[0], c[1]]).to_f32()).to_bits())
                .collect(),
            other => return Err(StError::Dtype(other.into(), name.into())),
        };
        Ok((ti.shape.clone(), out))
    }

    /// Decode to i32 (accepts I32, I64 with lossy narrow).
    pub fn i32(&self, name: &str) -> Result<(Vec<usize>, Vec<i32>), StError> {
        let (ti, b) = self.bytes(name)?;
        let out = match ti.dtype.as_str() {
            "I32" => b
                .chunks_exact(4)
                .map(|c| i32::from_le_bytes([c[0], c[1], c[2], c[3]]))
                .collect(),
            "I64" => b
                .chunks_exact(8)
                .map(|c| {
                    i64::from_le_bytes([c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7]]) as i32
                })
                .collect(),
            other => return Err(StError::Dtype(other.into(), name.into())),
        };
        Ok((ti.shape.clone(), out))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn tensor_file(
        header: serde_json::Value,
        bytes: &[u8],
        aligned: bool,
    ) -> tempfile::NamedTempFile {
        let mut file = tempfile::NamedTempFile::new().unwrap();
        let mut header = serde_json::to_vec(&header).unwrap();
        while header.len() % 8 != 0 {
            header.push(b' ');
        }
        if !aligned {
            header.push(b' ');
        }
        file.write_all(&(header.len() as u64).to_le_bytes())
            .unwrap();
        file.write_all(&header).unwrap();
        file.write_all(bytes).unwrap();
        file.flush().unwrap();
        file
    }

    #[test]
    fn mapped_bf16_owns_lifetime_and_preserves_all_bit_patterns() {
        let bits = [0u16, 0x8000, 0x3f80, 0x7f80, 0x7fc1, 0xffff];
        let bytes: Vec<u8> = bits.iter().flat_map(|b| b.to_le_bytes()).collect();
        let file = tensor_file(
            serde_json::json!({
                "w": {"dtype": "BF16", "shape": [2, 3], "data_offsets": [0, 12]}
            }),
            &bytes,
            true,
        );
        let owned = StFile::open(file.path()).unwrap();
        assert!(owned.mapped_bf16("w").unwrap().is_none());
        let mapped = StFile::open_mmap(file.path()).unwrap();
        assert_eq!(
            mapped.bf16_bits("w").unwrap(),
            owned.bf16_bits("w").unwrap()
        );
        let view = mapped.mapped_bf16("w").unwrap().unwrap();
        drop(mapped);
        assert_eq!(view.as_slice(), bits);
    }

    #[test]
    fn unaligned_and_f32_tensors_use_copy_fallback() {
        let file = tensor_file(
            serde_json::json!({
                "w": {"dtype": "BF16", "shape": [1], "data_offsets": [0, 2]}
            }),
            &0x3f80u16.to_le_bytes(),
            false,
        );
        let st = StFile::open_mmap(file.path()).unwrap();
        assert!(st.mapped_bf16("w").unwrap().is_none());
        assert_eq!(st.bf16_bits("w").unwrap().1, [0x3f80]);
        let file = tensor_file(
            serde_json::json!({
                "w": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}
            }),
            &1.0f32.to_le_bytes(),
            true,
        );
        let st = StFile::open_mmap(file.path()).unwrap();
        assert!(st.mapped_bf16("w").unwrap().is_none());
        assert_eq!(st.bf16_bits("w").unwrap().1, [0x3f80]);
    }

    #[test]
    fn malformed_offsets_are_errors_for_owned_and_mapped_readers() {
        for offsets in [
            serde_json::json!([0]),
            serde_json::json!([0, 3]),
            serde_json::json!([2, 0]),
            serde_json::json!([-1, 2]),
            serde_json::json!([0, u64::MAX]),
        ] {
            let file = tensor_file(
                serde_json::json!({
                    "w": {"dtype": "BF16", "shape": [1], "data_offsets": offsets}
                }),
                &[0, 0],
                true,
            );
            assert!(StFile::open(file.path()).is_err());
            assert!(StFile::open_mmap(file.path()).is_err());
        }
    }

    #[test]
    fn mapped_bf16_rejects_mismatched_or_overflowing_shape() {
        for shape in [serde_json::json!([2]), serde_json::json!([u64::MAX, 2])] {
            let file = tensor_file(
                serde_json::json!({
                    "w": {"dtype": "BF16", "shape": shape, "data_offsets": [0, 2]}
                }),
                &[0, 0],
                true,
            );
            let st = StFile::open_mmap(file.path()).unwrap();
            assert!(st.mapped_bf16("w").is_err());
        }
    }

    #[test]
    fn tensor_metadata_mutation_cannot_create_out_of_bounds_view() {
        let file = tensor_file(
            serde_json::json!({
                "w": {"dtype": "BF16", "shape": [1], "data_offsets": [0, 2]}
            }),
            &[0, 0],
            true,
        );
        let mut st = StFile::open_mmap(file.path()).unwrap();
        st.tensors.get_mut("w").unwrap().end = usize::MAX;
        assert!(st.mapped_bf16("w").is_err());
        assert!(st.bf16_bits("w").is_err());
    }

    #[test]
    fn oversized_header_returns_error_without_overflow() {
        let mut file = tempfile::NamedTempFile::new().unwrap();
        file.write_all(&u64::MAX.to_le_bytes()).unwrap();
        file.flush().unwrap();
        assert!(StFile::open(file.path()).is_err());
        assert!(StFile::open_mmap(file.path()).is_err());
    }
}
