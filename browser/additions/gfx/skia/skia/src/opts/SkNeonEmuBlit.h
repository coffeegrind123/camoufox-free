/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// Skia's AArch64 row blitters' per-pixel math at AVX2's width, for the
// emulated ARM64 tier (SkBlitRow_opts.h under SK_NEON_EMU). Each byte gets
// what SkPMSrcOver_neon8 gives it, so 8 pixels go through here and the
// 4-wide emulated loop finishes a row. browser/tests/neon-emu compares the
// two over every source alpha, source byte and destination byte.

#ifndef SkNeonEmuBlit_DEFINED
#define SkNeonEmuBlit_DEFINED

#if defined(__AVX2__)
#include <immintrin.h>

// SkMulDiv255Round_neon8 on 16-bit lanes holding bytes:
//   prod = x * y;  vraddhn_u16(prod, vrshrq_n_u16(prod, 8))
//   = (prod + ((prod + 128) >> 8) + 128) >> 8, which never exceeds 16 bits.
static inline __m256i sk_neon_emu_muldiv255round_epu16(__m256i x, __m256i y) {
  const __m256i half = _mm256_set1_epi16(128);
  __m256i prod = _mm256_mullo_epi16(x, y);
  __m256i rshr = _mm256_srli_epi16(_mm256_add_epi16(prod, half), 8);
  return _mm256_srli_epi16(_mm256_add_epi16(_mm256_add_epi16(prod, rshr), half), 8);
}

// SkPMSrcOver_neon8 for 8 RGBA pixels: src + (255 - srcA) * dst / 255,
// rounded, then a saturating add.
static inline __m256i sk_neon_emu_srcover_avx2(__m256i src, __m256i dst) {
  // Each pixel's alpha (byte 3) into all four of its bytes, inverted (vmvn_u8).
  const __m256i alpha = _mm256_setr_epi8(3, 3, 3, 3, 7, 7, 7, 7, 11, 11, 11, 11, 15, 15, 15, 15,
                                         3, 3, 3, 3, 7, 7, 7, 7, 11, 11, 11, 11, 15, 15, 15, 15);
  __m256i nalpha = _mm256_xor_si256(_mm256_shuffle_epi8(src, alpha), _mm256_set1_epi8(-1));
  const __m256i zero = _mm256_setzero_si256();
  // Unpack and pack both work within each 128-bit half, so bytes come back in place.
  __m256i lo = sk_neon_emu_muldiv255round_epu16(_mm256_unpacklo_epi8(nalpha, zero),
                                                _mm256_unpacklo_epi8(dst, zero));
  __m256i hi = sk_neon_emu_muldiv255round_epu16(_mm256_unpackhi_epi8(nalpha, zero),
                                                _mm256_unpackhi_epi8(dst, zero));
  return _mm256_adds_epu8(src, _mm256_packus_epi16(lo, hi));
}
#endif

#endif  // SkNeonEmuBlit_DEFINED
