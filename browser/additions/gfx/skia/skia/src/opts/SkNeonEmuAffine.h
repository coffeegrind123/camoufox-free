/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// AArch64 Skia draws rotated and skewed bitmaps through the legacy samplers:
// SkBitmapProcState_matrixProcs.cpp's filter_affine<clamp, clamp>, then the
// NEON S32_alpha_D32_filter_DXDY, one pixel at a time. Both are integer
// arithmetic; here they run four pixels at a time with the same bits, for
// the emulated ARM64 tier. browser/tests/neon-emu compares each with the
// code it replaces.
//
// filter_affine<clamp, clamp>: for each pixel, y then x,
//   f = (SkFixed)(f3232 >> 16)
//   (clamp(f) << 18) | (((f >> 12) & 0xf) << 14) | clamp(f + SK_Fixed1)
// with clamp(f) = SkTPin(f >> 16, 0, max), and f3232 += d3232 after each
// pixel, wrapping.
//
// filter_and_scale_by_alpha (NEON): per channel, with weights x, y in 0..16,
//   t = a00*(16-y)*(16-x) + a01*(16-y)*x + a10*y*(16-x) + a11*y*x
// in 16-bit lanes, which it never overflows (at most 255*256); then
// t = (t >> 8) * scale when scale < 256, and the byte t >> 8.

#ifndef SkNeonEmuAffine_DEFINED
#define SkNeonEmuAffine_DEFINED

#include <cstddef>
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

// Four pixels' bilerp: texel vectors hold one 8888 pixel per 32-bit lane,
// the weights one per 32-bit lane.
static inline __m128i sk_neon_emu_bilerp4(__m128i a00, __m128i a01, __m128i a10, __m128i a11,
                                          __m128i wx, __m128i wy, unsigned scale) {
  // Each pixel's weight into its four 16-bit channel lanes.
  const __m128i spread = _mm_setr_epi8(0, 0, 0, 0, 4, 4, 4, 4, 8, 8, 8, 8, 12, 12, 12, 12);
  const __m256i sixteen = _mm256_set1_epi16(16);
  __m256i x = _mm256_cvtepu8_epi16(_mm_shuffle_epi8(wx, spread)),
          y = _mm256_cvtepu8_epi16(_mm_shuffle_epi8(wy, spread)),
          ix = _mm256_sub_epi16(sixteen, x), iy = _mm256_sub_epi16(sixteen, y);
  __m256i t = _mm256_mullo_epi16(_mm256_cvtepu8_epi16(a00), _mm256_mullo_epi16(iy, ix));
  t = _mm256_add_epi16(t, _mm256_mullo_epi16(_mm256_cvtepu8_epi16(a01), _mm256_mullo_epi16(iy, x)));
  t = _mm256_add_epi16(t, _mm256_mullo_epi16(_mm256_cvtepu8_epi16(a10), _mm256_mullo_epi16(y, ix)));
  t = _mm256_add_epi16(t, _mm256_mullo_epi16(_mm256_cvtepu8_epi16(a11), _mm256_mullo_epi16(y, x)));
  if (scale < 256) {
    t = _mm256_mullo_epi16(_mm256_srli_epi16(t, 8), _mm256_set1_epi16((short)scale));
  }
  t = _mm256_srli_epi16(t, 8);
  // Pixels 0-1 and 2-3 pack into the low quadwords of the two halves.
  __m256i packed = _mm256_permute4x64_epi64(_mm256_packus_epi16(t, t), 0x08);
  return _mm256_castsi256_si128(packed);
}

// One pixel the same way, for a row's last pixels.
static inline uint32_t sk_neon_emu_bilerp1(uint32_t a00, uint32_t a01, uint32_t a10, uint32_t a11,
                                           unsigned x, unsigned y, unsigned scale) {
  uint32_t out = 0;
  for (int c = 0; c < 32; c += 8) {
    unsigned t = ((a00 >> c) & 0xff) * ((16 - y) * (16 - x)) + ((a01 >> c) & 0xff) * ((16 - y) * x) +
                 ((a10 >> c) & 0xff) * (y * (16 - x)) + ((a11 >> c) & 0xff) * (y * x);
    if (scale < 256) {
      t = (t >> 8) * scale;
    }
    out |= ((t >> 8) & 0xff) << c;
  }
  return out;
}

// S32_alpha_D32_filter_DXDY's loop: xy holds each pixel's packed y then x
// (decode_packed_coordinates_and_weight).
static inline void sk_neon_emu_filter_dxdy(const char* src, size_t rb, const uint32_t* xy, int count,
                                           uint32_t* colors, unsigned scale) {
  auto texels = [&](int i, uint32_t* a00, uint32_t* a01, uint32_t* a10, uint32_t* a11) {
    uint32_t py = xy[2 * i], px = xy[2 * i + 1];
    auto row0 = (const uint32_t*)(src + (py >> 18) * rb),
         row1 = (const uint32_t*)(src + (py & 0x3fff) * rb);
    unsigned x0 = px >> 18, x1 = px & 0x3fff;
    *a00 = row0[x0];
    *a01 = row0[x1];
    *a10 = row1[x0];
    *a11 = row1[x1];
  };
  for (; count >= 4; count -= 4) {
    uint32_t t[4][4];
    for (int i = 0; i < 4; i++) {
      texels(i, &t[0][i], &t[1][i], &t[2][i], &t[3][i]);
    }
    __m256i p = _mm256_loadu_si256((const __m256i*)xy);  // y0 x0 y1 x1 y2 x2 y3 x3
    __m256i w = _mm256_and_si256(_mm256_srli_epi32(p, 14), _mm256_set1_epi32(0xf));
    __m256i wy = _mm256_permutevar8x32_epi32(w, _mm256_setr_epi32(0, 2, 4, 6, 0, 2, 4, 6)),
            wx = _mm256_permutevar8x32_epi32(w, _mm256_setr_epi32(1, 3, 5, 7, 1, 3, 5, 7));
    __m128i out = sk_neon_emu_bilerp4(_mm_loadu_si128((const __m128i*)t[0]), _mm_loadu_si128((const __m128i*)t[1]),
                                      _mm_loadu_si128((const __m128i*)t[2]), _mm_loadu_si128((const __m128i*)t[3]),
                                      _mm256_castsi256_si128(wx), _mm256_castsi256_si128(wy), scale);
    _mm_storeu_si128((__m128i*)colors, out);
    xy += 8;
    colors += 4;
  }
  for (int i = 0; i < count; i++) {
    uint32_t a00, a01, a10, a11;
    texels(i, &a00, &a01, &a10, &a11);
    colors[i] = sk_neon_emu_bilerp1(a00, a01, a10, a11, (xy[2 * i + 1] >> 14) & 0xf, (xy[2 * i] >> 14) & 0xf,
                                    scale);
  }
}
#endif  // __AVX2__

#endif  // SkNeonEmuAffine_DEFINED
