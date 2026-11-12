// One build of the operations in ops.h, as NS_op_<name>(out, a, b, c, n): n
// independent calls, each on the next in0/in1/in2-byte inputs. check.py
// builds it three times (NS = ref, fast, base). The symbol is pasted from
// op_<name>, never from <name>, which may be a macro (SkNeonEmuShuffle.h).
#include <cstring>

#include "src/opts/SkNeonEmu.h"
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
