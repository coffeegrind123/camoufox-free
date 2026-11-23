/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// SkBitmapProcState_matrixProcs.cpp's filter_affine<clamp, clamp> at AVX2's
// width, for the emulated ARM64 tier: AArch64 Skia draws rotated and skewed
// bitmaps through the legacy samplers, which run this coordinate loop per
// pixel, while the host's own tier never reaches it. It is integer
// arithmetic, so the bits are the scalar loop's: for each pixel, y then x,
//   f = (SkFixed)(f3232 >> 16)
//   (clamp(f) << 18) | (((f >> 12) & 0xf) << 14) | clamp(f + SK_Fixed1)
// with clamp(f) = SkTPin(f >> 16, 0, max), and f3232 += d3232 after each
// pixel, wrapping. browser/tests/neon-emu compares it with that loop.

#ifndef SkNeonEmuAffine_DEFINED
#define SkNeonEmuAffine_DEFINED

#include <cstdint>

static inline uint32_t sk_neon_emu_pack_clamp(int32_t f, int32_t max) {
  auto clamp = [max](int32_t v) {
    v >>= 16;
    return (uint32_t)(v < 0 ? 0 : (v > max ? max : v));
  };
  uint32_t packed = clamp(f);
  packed = (packed << 4) | ((uint32_t)(f >> 12) & 0xf);
  packed = (packed << 14) | clamp((int32_t)((uint32_t)f + 0x10000u));
  return packed;
}

#if defined(__AVX2__)
#include <immintrin.h>

// Eight packed coordinates, pixel by pixel y then x, from eight SkFixed lanes
// in that order and their maxima.
static inline __m256i sk_neon_emu_pack_clamp8(__m256i f, __m256i max) {
  const __m256i zero = _mm256_setzero_si256();
  __m256i lo = _mm256_min_epi32(_mm256_max_epi32(_mm256_srai_epi32(f, 16), zero), max);
  __m256i hi = _mm256_add_epi32(f, _mm256_set1_epi32(0x10000));
  hi = _mm256_min_epi32(_mm256_max_epi32(_mm256_srai_epi32(hi, 16), zero), max);
  __m256i w = _mm256_and_si256(_mm256_srli_epi32(f, 12), _mm256_set1_epi32(0xf));
  return _mm256_or_si256(_mm256_or_si256(_mm256_slli_epi32(lo, 18), _mm256_slli_epi32(w, 14)), hi);
}

// The 64-bit lanes' bits 16..47, (SkFixed)(x >> 16), of a then b.
static inline __m256i sk_neon_emu_fixed8(__m256i a, __m256i b) {
  const __m256i even = _mm256_setr_epi32(0, 2, 4, 6, 0, 2, 4, 6);
  __m256i la = _mm256_permutevar8x32_epi32(_mm256_srli_epi64(a, 16), even),
          lb = _mm256_permutevar8x32_epi32(_mm256_srli_epi64(b, 16), even);
  return _mm256_permute2x128_si256(la, lb, 0x20);
}

static inline void sk_neon_emu_filter_affine_clamp(uint32_t xy[], int count, int64_t fx, int64_t fy,
                                                   int64_t dx, int64_t dy, int maxX, int maxY) {
  // Pixels i and i+1 in a, i+2 and i+3 in b, each as (y, x); the lane sums
  // wrap as the scalar loop's repeated adds do.
  auto add = [](int64_t p, int64_t q) { return (int64_t)((uint64_t)p + (uint64_t)q); };
  auto mul = [](int64_t p, int k) { return (int64_t)((uint64_t)p * (uint64_t)k); };
  __m256i a = _mm256_setr_epi64x(fy, fx, add(fy, dy), add(fx, dx)),
          b = _mm256_setr_epi64x(add(fy, mul(dy, 2)), add(fx, mul(dx, 2)),
                                 add(fy, mul(dy, 3)), add(fx, mul(dx, 3)));
  const __m256i step = _mm256_setr_epi64x(mul(dy, 4), mul(dx, 4), mul(dy, 4), mul(dx, 4));
  const __m256i max = _mm256_setr_epi32(maxY, maxX, maxY, maxX, maxY, maxX, maxY, maxX);
  for (; count >= 4; count -= 4) {
    _mm256_storeu_si256((__m256i*)xy, sk_neon_emu_pack_clamp8(sk_neon_emu_fixed8(a, b), max));
    xy += 8;
    a = _mm256_add_epi64(a, step);
    b = _mm256_add_epi64(b, step);
  }
  fy = _mm256_extract_epi64(a, 0);
  fx = _mm256_extract_epi64(a, 1);
  while (count-- > 0) {
    *xy++ = sk_neon_emu_pack_clamp((int32_t)(uint32_t)((uint64_t)fy >> 16), maxY);
    *xy++ = sk_neon_emu_pack_clamp((int32_t)(uint32_t)((uint64_t)fx >> 16), maxX);
    fy = add(fy, dy);
    fx = add(fx, dx);
  }
}
#endif  // __AVX2__

#endif  // SkNeonEmuAffine_DEFINED
