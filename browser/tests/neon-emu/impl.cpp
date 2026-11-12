// One build of the operations in ops.h, as NS_op_<name>(out, a, b, c, n): n
// independent calls, each on the next in0/in1/in2-byte inputs. check.py
// builds it three times (NS = ref, fast, base). The symbol is pasted from
// op_<name>, never from <name>, which may be a macro (SkNeonEmuShuffle.h).
#include <cstring>

#include "src/opts/SkNeonEmu.h"
#include "src/opts/SkNeonEmuBlit.h"
#include "ops.h"

#define NEON_EMU_CAT2(a, b) a##_##b
#define NEON_EMU_CAT(a, b) NEON_EMU_CAT2(a, b)

template <typename T>
static T ld(const unsigned char* p) {
  T v;
  memcpy(&v, p, sizeof v);
  return v;
}
template <typename T>
static void st(unsigned char* p, T v) {
  memcpy(p, &v, sizeof v);
}

#define UNARY(name, T)                                                        \
  extern "C" void NEON_EMU_CAT(NS, op_##name)(unsigned char* o, const unsigned char* a, \
                                         const unsigned char*, const unsigned char*, \
                                         unsigned long n) {                   \
    for (unsigned long i = 0; i < n; i++) {                                   \
      auto r = name(ld<T>(a + i * sizeof(T)));                                \
      st(o + i * sizeof(r), r);                                               \
    }                                                                         \
  }
#define BINARY(name, T)                                                       \
  extern "C" void NEON_EMU_CAT(NS, op_##name)(unsigned char* o, const unsigned char* a, \
                                         const unsigned char* b, const unsigned char*, \
                                         unsigned long n) {                   \
    for (unsigned long i = 0; i < n; i++) {                                   \
      auto r = name(ld<T>(a + i * 16), ld<T>(b + i * 16));                    \
      st(o + i * 16, r);                                                      \
    }                                                                         \
  }
#define TERNARY(name)                                                         \
  extern "C" void NEON_EMU_CAT(NS, op_##name)(unsigned char* o, const unsigned char* a, \
                                         const unsigned char* b, const unsigned char* c, \
                                         unsigned long n) {                   \
    for (unsigned long i = 0; i < n; i++) {                                   \
      st(o + i * 16, name(ld<float32x4_t>(a + i * 16), ld<float32x4_t>(b + i * 16), \
                          ld<float32x4_t>(c + i * 16)));                      \
    }                                                                         \
  }
#define LOAD(name, S, T, BYTES)                                               \
  extern "C" void NEON_EMU_CAT(NS, op_##name)(unsigned char* o, const unsigned char* a, \
                                         const unsigned char*, const unsigned char*, \
                                         unsigned long n) {                   \
    for (unsigned long i = 0; i < n; i++) {                                   \
      S r = name((const T*)(const void*)(a + i * BYTES));                     \
      memcpy(o + i * BYTES, &r, BYTES);                                       \
    }                                                                         \
  }
#define STORE(name, S, T, BYTES)                                              \
  extern "C" void NEON_EMU_CAT(NS, op_##name)(unsigned char* o, const unsigned char* a, \
                                         const unsigned char*, const unsigned char*, \
                                         unsigned long n) {                   \
    for (unsigned long i = 0; i < n; i++) {                                   \
      name((T*)(void*)(o + i * BYTES), ld<S>(a + i * BYTES));                 \
    }                                                                         \
  }

#define EXPR1(id, T0, expr)                                                   \
  extern "C" void NEON_EMU_CAT(NS, op_##id)(unsigned char* o, const unsigned char* a, \
                                            const unsigned char*, const unsigned char*, \
                                            unsigned long n) {                \
    for (unsigned long i = 0; i < n; i++) {                                   \
      T0 x = ld<T0>(a + i * sizeof(T0));                                      \
      auto r = (expr);                                                        \
      st(o + i * sizeof(r), r);                                               \
    }                                                                         \
  }
#define EXPR2(id, T0, T1, expr)                                               \
  extern "C" void NEON_EMU_CAT(NS, op_##id)(unsigned char* o, const unsigned char* a, \
                                            const unsigned char* b, const unsigned char*, \
                                            unsigned long n) {                \
    for (unsigned long i = 0; i < n; i++) {                                   \
      T0 x = ld<T0>(a + i * sizeof(T0));                                      \
      T1 y = ld<T1>(b + i * sizeof(T1));                                      \
      auto r = (expr);                                                        \
      st(o + i * sizeof(r), r);                                               \
    }                                                                         \
  }

UNARY(vrecpeq_f32, float32x4_t)
UNARY(vrsqrteq_f32, float32x4_t)
UNARY(vsqrtq_f32, float32x4_t)
UNARY(vcvtq_s32_f32, float32x4_t)
UNARY(vcvtq_u32_f32, float32x4_t)
UNARY(vcvtnq_s32_f32, float32x4_t)
UNARY(vcvtnq_u32_f32, float32x4_t)
UNARY(vcvt_f16_f32, float32x4_t)
UNARY(vcvt_f32_f16, float16x4_t)
BINARY(vrecpsq_f32, float32x4_t)
BINARY(vrsqrtsq_f32, float32x4_t)
BINARY(vmulq_f32, float32x4_t)
BINARY(vaddq_f32, float32x4_t)
BINARY(vsubq_f32, float32x4_t)
BINARY(vminq_f32, float32x4_t)
BINARY(vmaxq_f32, float32x4_t)
BINARY(vqrdmulhq_s16, int16x8_t)
TERNARY(vfmaq_f32)
TERNARY(vfmsq_f32)
LOAD(vld2_u8, uint8x8x2_t, uint8_t, 16)
LOAD(vld2q_u8, uint8x16x2_t, uint8_t, 32)
LOAD(vld3_u8, uint8x8x3_t, uint8_t, 24)
LOAD(vld3q_u8, uint8x16x3_t, uint8_t, 48)
LOAD(vld4_u8, uint8x8x4_t, uint8_t, 32)
LOAD(vld4q_u8, uint8x16x4_t, uint8_t, 64)
LOAD(vld2_u16, uint16x4x2_t, uint16_t, 16)
LOAD(vld2q_u16, uint16x8x2_t, uint16_t, 32)
LOAD(vld4_u16, uint16x4x4_t, uint16_t, 32)
LOAD(vld4q_u16, uint16x8x4_t, uint16_t, 64)
LOAD(vld4q_f32, float32x4x4_t, float, 64)
STORE(vst2_u8, uint8x8x2_t, uint8_t, 16)
STORE(vst2q_u8, uint8x16x2_t, uint8_t, 32)
STORE(vst4_u8, uint8x8x4_t, uint8_t, 32)
STORE(vst4q_u8, uint8x16x4_t, uint8_t, 64)
STORE(vst2_u16, uint16x4x2_t, uint16_t, 16)
STORE(vst2q_u16, uint16x8x2_t, uint16_t, 32)
STORE(vst4_u16, uint16x4x4_t, uint16_t, 32)
STORE(vst4q_u16, uint16x8x4_t, uint16_t, 64)
STORE(vst4q_f32, float32x4x4_t, float, 64)
EXPR1(vrshrq_n_u16_1, uint16x8_t, vrshrq_n_u16(x, 1))
EXPR1(vrshrq_n_u16_8, uint16x8_t, vrshrq_n_u16(x, 8))
EXPR1(vrshrq_n_u16_15, uint16x8_t, vrshrq_n_u16(x, 15))
EXPR1(vrshr_n_u8_4, uint8x8_t, vrshr_n_u8(x, 4))
EXPR1(vrshrq_n_s16_7, int16x8_t, vrshrq_n_s16(x, 7))
EXPR2(vrsraq_n_u16_8, uint16x8_t, uint16x8_t, vrsraq_n_u16(x, y, 8))
EXPR1(vshrn_n_u16_8, uint16x8_t, vshrn_n_u16(x, 8))
EXPR1(vrshrn_n_u16_8, uint16x8_t, vrshrn_n_u16(x, 8))
EXPR1(vrshrn_n_u16_3, uint16x8_t, vrshrn_n_u16(x, 3))
EXPR1(vqrshrn_n_u16_6, uint16x8_t, vqrshrn_n_u16(x, 6))
EXPR2(vraddhn_u16, uint16x8_t, uint16x8_t, vraddhn_u16(x, y))
EXPR2(vaddhn_u16, uint16x8_t, uint16x8_t, vaddhn_u16(x, y))
EXPR1(vqmovn_u16, uint16x8_t, vqmovn_u16(x))
EXPR1(vmovn_u16, uint16x8_t, vmovn_u16(x))
EXPR1(vmovl_u8, uint8x8_t, vmovl_u8(x))
EXPR1(vmovl_u16, uint16x4_t, vmovl_u16(x))
EXPR2(vqadd_u8, uint8x8_t, uint8x8_t, vqadd_u8(x, y))
EXPR2(vqaddq_u8, uint8x16_t, uint8x16_t, vqaddq_u8(x, y))
EXPR2(vqsub_u8, uint8x8_t, uint8x8_t, vqsub_u8(x, y))
EXPR2(vqsubq_u8, uint8x16_t, uint8x16_t, vqsubq_u8(x, y))
EXPR2(vmin_u8, uint8x8_t, uint8x8_t, vmin_u8(x, y))
EXPR2(vmax_u8, uint8x8_t, uint8x8_t, vmax_u8(x, y))
EXPR2(vtbl1_u8, uint8x8_t, uint8x8_t, vtbl1_u8(x, y))
EXPR2(vqtbl1q_u8, uint8x16_t, uint8x16_t, vqtbl1q_u8(x, y))
EXPR2(vqtbl1_u8, uint8x16_t, uint8x8_t, vqtbl1_u8(x, y))
EXPR1(vrev32q_u8, uint8x16_t, vrev32q_u8(x))

// SkBlitRow_opts.h's AArch64 source-over (SkPMSrcOver_neon8), 8 pixels at a
// time: through the lane-wise intrinsics in ref and base, through the AVX2
// kernel the emulated blitter uses (SkNeonEmuBlit.h) in fast.
#if !NEON_EMU_FAST
static uint8x8_t srcover_muldiv255round(uint8x8_t x, uint8x8_t y) {
  uint16x8_t prod = vmull_u8(x, y);
  return vraddhn_u16(prod, vrshrq_n_u16(prod, 8));
}
#endif
extern "C" void NEON_EMU_CAT(NS, op_srcover8)(unsigned char* o, const unsigned char* a,
                                             const unsigned char* b, const unsigned char*,
                                             unsigned long n) {
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256i src = _mm256_loadu_si256((const __m256i*)(a + i * 32));
    __m256i dst = _mm256_loadu_si256((const __m256i*)(b + i * 32));
    _mm256_storeu_si256((__m256i*)(o + i * 32), sk_neon_emu_srcover_avx2(src, dst));
#else
    uint8x8x4_t src = vld4_u8(a + i * 32), dst = vld4_u8(b + i * 32);
    uint8x8_t na = vmvn_u8(src.val[3]);
    uint8x8x4_t r = {{
        vqadd_u8(src.val[0], srcover_muldiv255round(na, dst.val[0])),
        vqadd_u8(src.val[1], srcover_muldiv255round(na, dst.val[1])),
        vqadd_u8(src.val[2], srcover_muldiv255round(na, dst.val[2])),
        vqadd_u8(src.val[3], srcover_muldiv255round(na, dst.val[3])),
    }};
    vst4_u8(o + i * 32, r);
#endif
  }
}
