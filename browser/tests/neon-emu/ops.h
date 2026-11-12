/* The SkNeonEmu.h operations with a fast path or a shuffle, as
 *   X(name, in0 bytes, in1 bytes, in2 bytes, out bytes, kind)
 * kind: F = float lanes in, U = integer lanes in, M = memory (load/store). */
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
  X(vst4q_f32, 64, 0, 0, 64, M)

typedef void (*neon_emu_op)(unsigned char* out, const unsigned char* a, const unsigned char* b,
                            const unsigned char* c, unsigned long n);
