// One build of the operations in ops.h, as NS_op_<name>(out, a, b, c, n): n
// independent calls, each on the next in0/in1/in2-byte inputs. check.py
// builds it three times (NS = ref, fast, base). The symbol is pasted from
// op_<name>, never from <name>, which may be a macro (SkNeonEmuShuffle.h).
#include <cstring>

#include "src/opts/SkNeonEmu.h"
#include "src/opts/SkNeonEmuAffine.h"
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

// SkNeonEmuWide.h's 8-lane forms (fast) against the 4-lane functions on each
// half (ref, base).
extern "C" void NEON_EMU_CAT(NS, op_w8_fma)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) {
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    __m256 WB = _mm256_loadu_ps((const float*)(b + i * 32));
    __m256 WC = _mm256_loadu_ps((const float*)(c + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), neon_emu_fma8(WA,WB,WC));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vfmaq_f32(ld<float32x4_t>(a + i * 32 + h * 16), ld<float32x4_t>(b + i * 32 + h * 16), ld<float32x4_t>(c + i * 32 + h * 16)));
#endif
  }
}
extern "C" void NEON_EMU_CAT(NS, op_w8_fms)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) {
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    __m256 WB = _mm256_loadu_ps((const float*)(b + i * 32));
    __m256 WC = _mm256_loadu_ps((const float*)(c + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), neon_emu_fms8(WA,WB,WC));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vfmsq_f32(ld<float32x4_t>(a + i * 32 + h * 16), ld<float32x4_t>(b + i * 32 + h * 16), ld<float32x4_t>(c + i * 32 + h * 16)));
#endif
  }
}
extern "C" void NEON_EMU_CAT(NS, op_w8_min)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    __m256 WB = _mm256_loadu_ps((const float*)(b + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), neon_emu_min8(WA,WB));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vminq_f32(ld<float32x4_t>(a + i * 32 + h * 16), ld<float32x4_t>(b + i * 32 + h * 16)));
#endif
  }
}
extern "C" void NEON_EMU_CAT(NS, op_w8_max)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    __m256 WB = _mm256_loadu_ps((const float*)(b + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), neon_emu_max8(WA,WB));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vmaxq_f32(ld<float32x4_t>(a + i * 32 + h * 16), ld<float32x4_t>(b + i * 32 + h * 16)));
#endif
  }
}
extern "C" void NEON_EMU_CAT(NS, op_w8_abs)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)b; (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), neon_emu_abs8(WA));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vabsq_f32(ld<float32x4_t>(a + i * 32 + h * 16)));
#endif
  }
}
extern "C" void NEON_EMU_CAT(NS, op_w8_floor)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)b; (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), neon_emu_floor8(WA));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vrndmq_f32(ld<float32x4_t>(a + i * 32 + h * 16)));
#endif
  }
}
extern "C" void NEON_EMU_CAT(NS, op_w8_ceil)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)b; (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), neon_emu_ceil8(WA));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vrndpq_f32(ld<float32x4_t>(a + i * 32 + h * 16)));
#endif
  }
}
extern "C" void NEON_EMU_CAT(NS, op_w8_sqrt)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)b; (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), neon_emu_sqrt8(WA));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vsqrtq_f32(ld<float32x4_t>(a + i * 32 + h * 16)));
#endif
  }
}
extern "C" void NEON_EMU_CAT(NS, op_w8_recpe)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)b; (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), neon_emu_recpe8(WA));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vrecpeq_f32(ld<float32x4_t>(a + i * 32 + h * 16)));
#endif
  }
}
extern "C" void NEON_EMU_CAT(NS, op_w8_rsqrte)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)b; (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), neon_emu_rsqrte8(WA));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vrsqrteq_f32(ld<float32x4_t>(a + i * 32 + h * 16)));
#endif
  }
}
extern "C" void NEON_EMU_CAT(NS, op_w8_recps)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    __m256 WB = _mm256_loadu_ps((const float*)(b + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), neon_emu_recps8(WA,WB));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vrecpsq_f32(ld<float32x4_t>(a + i * 32 + h * 16), ld<float32x4_t>(b + i * 32 + h * 16)));
#endif
  }
}
extern "C" void NEON_EMU_CAT(NS, op_w8_rsqrts)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    __m256 WB = _mm256_loadu_ps((const float*)(b + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), neon_emu_rsqrts8(WA,WB));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vrsqrtsq_f32(ld<float32x4_t>(a + i * 32 + h * 16), ld<float32x4_t>(b + i * 32 + h * 16)));
#endif
  }
}
extern "C" void NEON_EMU_CAT(NS, op_w8_cvtns)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)b; (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), _mm256_castsi256_ps(neon_emu_cvtns8(WA)));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vcvtnq_s32_f32(ld<float32x4_t>(a + i * 32 + h * 16)));
#endif
  }
}
extern "C" void NEON_EMU_CAT(NS, op_w8_cvtnu)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)b; (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), _mm256_castsi256_ps(neon_emu_cvtnu8(WA)));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vcvtnq_u32_f32(ld<float32x4_t>(a + i * 32 + h * 16)));
#endif
  }
}

// SkNeonEmuAffine.h against filter_affine<clamp, clamp>'s loop as
// SkBitmapProcState_matrixProcs.cpp writes it. Random positions and steps,
// each shifted down by 0..31 bits so that every magnitude occurs, from
// in-range draws to wrapping sums; maxima up to 14 bits; 0..13 pixels.
// SkTPin(f >> 16, 0, max): std::max(0, std::min(v, max)).
static uint32_t stock_clamp(int32_t f, int max) {
  int v = f >> 16;
  v = v < max ? v : max;
  return (uint32_t)(v > 0 ? v : 0);
}
static uint32_t stock_pack(int32_t f, int max) {
  uint32_t p = stock_clamp(f, max);
  p = (p << 4) | ((uint32_t)(f >> 12) & 0xf);
  p = (p << 14) | stock_clamp((int32_t)((uint32_t)f + 0x10000u), max);
  return p;
}
extern "C" void NEON_EMU_CAT(NS, op_affine_clamp)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)c;
  for (unsigned long i = 0; i < n; i++) {
    int64_t r[4];
    uint32_t m[4];
    memcpy(r, a + i * 32, sizeof r);
    memcpy(m, b + i * 16, sizeof m);
    for (int k = 0; k < 4; k++) r[k] >>= (m[3] >> (5 * k)) & 31;
    int maxX = (int)(m[0] & 0x3fff), maxY = (int)(m[1] & 0x3fff), count = (int)(m[2] % 14);
    uint32_t xy[26] = {};
#if NEON_EMU_FAST
    sk_neon_emu_filter_affine_clamp(xy, count, r[0], r[1], r[2], r[3], maxX, maxY);
#else
    int64_t fx = r[0], fy = r[1];
    for (int k = 0; k < count; k++) {
      xy[2 * k] = stock_pack((int32_t)(fy >> 16), maxY);
      xy[2 * k + 1] = stock_pack((int32_t)(fx >> 16), maxX);
      fy = (int64_t)((uint64_t)fy + (uint64_t)r[3]);
      fx = (int64_t)((uint64_t)fx + (uint64_t)r[2]);
    }
#endif
    memcpy(o + i * 104, xy, sizeof xy);
  }
}

// SkRasterPipeline_opts.h's lowp div255 under SKRP_ARM_SEMANTICS, against
// the AArch64 tier's VRSRA and VRSHR.
extern "C" void NEON_EMU_CAT(NS, op_w16_div255)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)b; (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256i WA = _mm256_loadu_si256((const __m256i*)(a + i * 32));
    _mm256_storeu_si256((__m256i*)(o + i * 32), neon_emu_div255_16(WA));
#else
    for (int h = 0; h < 2; h++) {
      uint16x8_t v = ld<uint16x8_t>(a + i * 32 + h * 16);
      st(o + i * 32 + h * 16, vrshrq_n_u16(vrsraq_n_u16(v, v, 8), 8));
    }
#endif
  }
}

// SkRasterPipeline_opts.h's clamp_01_ and to_unorm(v, 255) under
// SKRP_ARM_SEMANTICS, against the 4-lane FMAX, FMIN, FMLA and FCVTNU they
// stand for, in Skia's operand order.
extern "C" void NEON_EMU_CAT(NS, op_w8_clamp01)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)b; (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), neon_emu_clamp01_8(WA));
#else
    for (int h = 0; h < 2; h++) st(o + i * 32 + h * 16, vminq_f32(vmaxq_f32(vdupq_n_f32(0.0f), ld<float32x4_t>(a + i * 32 + h * 16)), vdupq_n_f32(1.0f)));
#endif
  }
}
extern "C" void NEON_EMU_CAT(NS, op_w8_unorm255)(unsigned char* o, const unsigned char* a,
                                          const unsigned char* b, const unsigned char* c,
                                          unsigned long n) { (void)b; (void)c;
  for (unsigned long i = 0; i < n; i++) {
#if NEON_EMU_FAST
    __m256 WA = _mm256_loadu_ps((const float*)(a + i * 32));
    _mm256_storeu_ps((float*)(o + i * 32), _mm256_castsi256_ps(neon_emu_unorm8(WA, 255.0f, 0.0f, 255.0f)));
#else
    for (int h = 0; h < 2; h++) {
      float32x4_t t = vfmaq_f32(vdupq_n_f32(0.0f), ld<float32x4_t>(a + i * 32 + h * 16), vdupq_n_f32(255.0f));
      st(o + i * 32 + h * 16, vcvtnq_u32_f32(vminq_f32(vmaxq_f32(vdupq_n_f32(0.0f), t), vdupq_n_f32(255.0f))));
    }
#endif
  }
}
