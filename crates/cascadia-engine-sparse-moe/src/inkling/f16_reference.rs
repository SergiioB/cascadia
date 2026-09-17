//! Diagnostic CPU reference for the compact GPU graph's FP16 boundaries.
//!
//! This is not the normal BF16 Inkling CPU path. It independently decodes the
//! original packed bins, applies the IR's scale conversion, and rounds inputs,
//! gate/up GEMMs, SwiGLU output and down GEMM to FP16. FP32 accumulation and
//! exp can differ slightly from GPU reduction order/native_exp. Routing stays
//! outside this function, in FP32, as in the compact GPU worker.
use half::{bf16, f16};

pub(super) struct Prepared {
    scales: [Vec<u8>; 3],
    hidden: usize,
    inter: usize,
    scale: f32,
}

fn half_round(v: f32) -> f32 {
    f16::from_f32(v).to_f32()
}

impl Prepared {
    pub(super) fn new(data: &[u8], hidden: usize, inter: usize) -> Result<Self, String> {
        let matrix = hidden * inter;
        let section = matrix / 2 + matrix / 16;
        if !hidden.is_multiple_of(32) || !inter.is_multiple_of(32) || data.len() != section * 3 {
            return Err("FP16 reference requires complete group-32 int4 experts".into());
        }
        let scale = 16.;
        let scales = std::array::from_fn(|m| {
            data[m * section + matrix / 2..(m + 1) * section]
                .chunks_exact(2)
                .flat_map(|b| {
                    let original = bf16::from_le_bytes([b[0], b[1]]).to_f32();
                    // Match two export steps: original BF16 -> FP16, then
                    // optional power-of-two attenuation and FP16 storage.
                    let value = half_round(half_round(original) / if m == 1 { scale } else { 1. });
                    bf16::from_f32(value).to_le_bytes()
                })
                .collect()
        });
        Ok(Self {
            scales,
            hidden,
            inter,
            scale,
        })
    }

    pub(super) fn forward(&self, data: &[u8], x: &[f32]) -> Vec<f32> {
        let matrix = self.hidden * self.inter;
        let section = matrix / 2 + matrix / 16;
        let gemv = |m: usize, input: &[f32], out: usize, inn: usize| {
            let packed = &data[m * section..m * section + matrix / 2];
            let mut y = vec![0.; out];
            cascadia_int4_gemm::dequant_gemv_int4_auto(
                packed,
                &self.scales[m],
                input,
                out,
                inn,
                &mut y,
            );
            y.iter_mut().for_each(|v| *v = half_round(*v));
            y
        };
        let x: Vec<f32> = x.iter().map(|&v| half_round(v)).collect();
        let mut gate = gemv(0, &x, self.inter, self.hidden);
        let up = gemv(1, &x, self.inter, self.hidden);
        for (g, u) in gate.iter_mut().zip(up) {
            *g = half_round((*g / (1. + (-*g).exp())) * u);
        }
        let mut out = gemv(2, &gate, self.hidden, self.inter);
        out.iter_mut().for_each(|v| *v *= self.scale);
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn independent_uniform_matrix_result_includes_half_boundaries_and_rescale() {
        let (h, i) = (32, 32);
        let mut data = Vec::new();
        for _ in 0..3 {
            data.extend(vec![0x99; h * i / 2]); // Every signed nibble = 1.
            for _ in 0..h * i / 32 {
                data.extend(bf16::from_f32(0.125).to_le_bytes());
            }
        }
        let x = vec![0.125; h];
        let p = Prepared::new(&data, h, i).unwrap();
        let g = 0.5f32;
        let a = half_round(g / (1. + (-g).exp()) * (g / 16.));
        let expected = half_round(a * 4.) * 16.;
        assert_eq!(p.forward(&data, &x), vec![expected; h]);
        assert!(Prepared::new(&data[..data.len() - 1], h, i).is_err());
    }
}
