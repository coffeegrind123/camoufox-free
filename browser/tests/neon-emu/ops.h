/* The SkNeonEmu.h operations with a fast path or a shuffle, as
 *   X(name, in0 bytes, in1 bytes, in2 bytes, out bytes, kind)
 * kind: F = float lanes in, U = integer lanes in, M = memory (load/store).
 * An integer operation with an immediate is listed once per tested count. */
#define NEON_EMU_OPS(X)                         \
  X(vrecpeq_f32, 16, 0, 0, 16, F)               \
  X(vrsqrteq_f32, 16, 0, 0, 16, F)              \
  X(vsqrtq_f32, 16, 0, 0, 16, F)                \
  X(vcvtq_s32_f32, 16, 0, 0, 16, F)             \
  X(vcvtq_u32_f32, 16, 0, 0, 16, F)             \
  X(vcvtnq_s32_f32, 16, 0, 0, 16, F)            \
  X(vcvtnq_u32_f32, 16, 0, 0, 16, F)            \
  X(vcvt_f16_f32, 16, 0, 0, 8, F)               \
  X(vcvt_f32_f16, 8, 0, 0, 16, U)               \
  X(vrecpsq_f32, 16, 16, 0, 16, F)              \
  X(vrsqrtsq_f32, 16, 16, 0, 16, F)             \
  X(vmulq_f32, 16, 16, 0, 16, F)                \
  X(vaddq_f32, 16, 16, 0, 16, F)                \
  X(vsubq_f32, 16, 16, 0, 16, F)                \
  X(vminq_f32, 16, 16, 0, 16, F)                \
  X(vmaxq_f32, 16, 16, 0, 16, F)                \
  X(vfmaq_f32, 16, 16, 16, 16, F)               \
  X(vfmsq_f32, 16, 16, 16, 16, F)               \
  X(vqrdmulhq_s16, 16, 16, 0, 16, U)            \
  X(vld2_u8, 16, 0, 0, 16, M)                   \
  X(vld2q_u8, 32, 0, 0, 32, M)                  \
  X(vld3_u8, 24, 0, 0, 24, M)                   \
  X(vld3q_u8, 48, 0, 0, 48, M)                  \
  X(vld4_u8, 32, 0, 0, 32, M)                   \
  X(vld4q_u8, 64, 0, 0, 64, M)                  \
  X(vld2_u16, 16, 0, 0, 16, M)                  \
  X(vld2q_u16, 32, 0, 0, 32, M)                 \
  X(vld4_u16, 32, 0, 0, 32, M)                  \
  X(vld4q_u16, 64, 0, 0, 64, M)                 \
  X(vld4q_f32, 64, 0, 0, 64, M)                 \
  X(vst2_u8, 16, 0, 0, 16, M)                   \
  X(vst2q_u8, 32, 0, 0, 32, M)                  \
  X(vst4_u8, 32, 0, 0, 32, M)                   \
  X(vst4q_u8, 64, 0, 0, 64, M)                  \
  X(vst2_u16, 16, 0, 0, 16, M)                  \
  X(vst2q_u16, 32, 0, 0, 32, M)                 \
  X(vst4_u16, 32, 0, 0, 32, M)                  \
  X(vst4q_u16, 64, 0, 0, 64, M)                 \
  X(vst4q_f32, 64, 0, 0, 64, M)                 \
  X(vrshrq_n_u16_1, 16, 0, 0, 16, U)          \
  X(vrshrq_n_u16_8, 16, 0, 0, 16, U)          \
  X(vrshrq_n_u16_15, 16, 0, 0, 16, U)         \
  X(vrshr_n_u8_4, 8, 0, 0, 8, U)              \
  X(vrshrq_n_s16_7, 16, 0, 0, 16, U)          \
  X(vrsraq_n_u16_8, 16, 16, 0, 16, U)         \
  X(vshrn_n_u16_8, 16, 0, 0, 8, U)            \
  X(vrshrn_n_u16_8, 16, 0, 0, 8, U)           \
  X(vrshrn_n_u16_3, 16, 0, 0, 8, U)           \
  X(vqrshrn_n_u16_6, 16, 0, 0, 8, U)          \
  X(vraddhn_u16, 16, 16, 0, 8, U)             \
  X(vaddhn_u16, 16, 16, 0, 8, U)              \
  X(vqmovn_u16, 16, 0, 0, 8, U)               \
  X(vmovn_u16, 16, 0, 0, 8, U)                \
  X(vmovl_u8, 8, 0, 0, 16, U)                 \
  X(vmovl_u16, 8, 0, 0, 16, U)                \
  X(vqadd_u8, 8, 8, 0, 8, U)                  \
  X(vqaddq_u8, 16, 16, 0, 16, U)              \
  X(vqsub_u8, 8, 8, 0, 8, U)                  \
  X(vqsubq_u8, 16, 16, 0, 16, U)              \
  X(vmin_u8, 8, 8, 0, 8, U)                   \
  X(vmax_u8, 8, 8, 0, 8, U)                   \
  X(vtbl1_u8, 8, 8, 0, 8, U)                  \
  X(vqtbl1q_u8, 16, 16, 0, 16, U)             \
  X(vqtbl1_u8, 16, 8, 0, 8, U)                \
  X(vrev32q_u8, 16, 0, 0, 16, U)                \
  X(srcover8, 32, 32, 0, 32, U) \
  X(w8_fma, 32, 32, 32, 32, F) \
  X(w8_fms, 32, 32, 32, 32, F) \
  X(w8_min, 32, 32, 0, 32, F) \
  X(w8_max, 32, 32, 0, 32, F) \
  X(w8_abs, 32, 0, 0, 32, F) \
  X(w8_floor, 32, 0, 0, 32, F) \
  X(w8_ceil, 32, 0, 0, 32, F) \
  X(w8_sqrt, 32, 0, 0, 32, F) \
  X(w8_recpe, 32, 0, 0, 32, F) \
  X(w8_rsqrte, 32, 0, 0, 32, F) \
  X(w8_recps, 32, 32, 0, 32, F) \
  X(w8_rsqrts, 32, 32, 0, 32, F) \
  X(w8_cvtns, 32, 0, 0, 32, F) \
  X(w8_cvtnu, 32, 0, 0, 32, F)

typedef void (*neon_emu_op)(unsigned char* out, const unsigned char* a, const unsigned char* b,
                            const unsigned char* c, unsigned long n);
