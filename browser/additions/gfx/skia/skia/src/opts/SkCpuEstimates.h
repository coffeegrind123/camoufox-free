/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/*
 * RCPPS and RSQRTPS as another x86 vendor's CPU computes them.
 *
 * The two estimate instructions are specified only to a relative error of
 * 1.5 * 2^-12, and Intel and AMD implement them with different tables: the
 * same input gives different bits on the two vendors, and the same bits on
 * every generation of one vendor (Intel 11th and 12th gen, AMD Zen 4 and
 * Zen 5 agree over all 2^32 inputs). Skia's raster pipeline uses them for
 * blend modes, perspective and matrix inversion, so a canvas a page reads back
 * shows which vendor drew it.
 *
 * A table holds the instruction's output for inputs 1.m (rcp) and for inputs
 * 1.m and 2.m (rsqrt), indexed by the top 12 mantissa bits; the output's
 * mantissa does not depend on the input's exponent. Intel's outputs depend on
 * fewer bits (11 for rcp, 10 for rsqrt) and its table repeats them. With the
 * recorded tables (SkCpuEstimateTables.h) these functions reproduce both
 * vendors' instructions for every input, special values included;
 * browser/tests/cpu-estimates/check.py runs that comparison.
 *
 * Plain C, so the check compiles exactly this code.
 */

#ifndef SkCpuEstimates_DEFINED
#define SkCpuEstimates_DEFINED

#include <stdint.h>

#define SK_CPU_ESTIMATE_BITS 12
#define SK_CPU_ESTIMATE_ENTRIES (1 << SK_CPU_ESTIMATE_BITS)
/* rcp[4096], rsqrt of 1.m[4096], rsqrt of 2.m[4096] */
#define SK_CPU_ESTIMATE_TABLE_SIZE (3 * SK_CPU_ESTIMATE_ENTRIES)

enum {
  SK_CPU_VENDOR_HOST = 0,
  SK_CPU_VENDOR_INTEL = 1,
  SK_CPU_VENDOR_AMD = 2,
  SK_CPU_IDENTITY_ARM64 = 3,
};

static inline uint32_t sk_cpu_estimate_rcp(const uint32_t* table, uint32_t b) {
  uint32_t s = b & 0x80000000u, e = (b >> 23) & 0xff;
  if (e == 0xff) {
    return (b & 0x7fffff) ? (b | 0x400000u) : s; /* NaN is quieted, 1/inf is 0 */
  }
  if (e == 0) {
    return s | 0x7f800000u; /* zero and denormals give infinity */
  }
  uint32_t t = table[(b & 0x7fffff) >> (23 - SK_CPU_ESTIMATE_BITS)];
  int oe = (int)((t >> 23) & 0xff) + 127 - (int)e;
  if (oe <= 0) {
    return s; /* a result below the normal range is flushed to 0 */
  }
  return s | ((uint32_t)oe << 23) | (t & 0x7fffff);
}

static inline uint32_t sk_cpu_estimate_rsqrt(const uint32_t* table, uint32_t b) {
  uint32_t s = b & 0x80000000u, e = (b >> 23) & 0xff;
  if (e == 0xff) {
    return (b & 0x7fffff) ? (b | 0x400000u) : (s ? 0xffc00000u : 0);
  }
  if (e == 0) {
    return s | 0x7f800000u;
  }
  if (s) {
    return 0xffc00000u; /* a negative input gives the default NaN */
  }
  int p = ((int)e - 127) & 1;
  uint32_t t = table[(1 + p) * SK_CPU_ESTIMATE_ENTRIES +
                     ((b & 0x7fffff) >> (23 - SK_CPU_ESTIMATE_BITS))];
  int oe = (int)((t >> 23) & 0xff) - (((int)e - 127 - p) / 2);
  return ((uint32_t)oe << 23) | (t & 0x7fffff);
}

/*
 * The same two functions on whole vectors, for the raster pipeline's SSE and
 * HSW tiers: one table load per lane and the special cases as selects, applied
 * in the reverse order of the scalar code's branches so the earliest branch
 * wins. Every input gives the scalar functions' bits; estimates.c `vcheck`
 * compares them over all 2^32 inputs. Out-of-range lanes (NaN, infinity, zero,
 * denormals) still index the table with their own mantissa, always in range.
 */
#if defined(__SSE2__)
#include <emmintrin.h>

static inline __m128i sk_cpu_estimate_select_sse2(__m128i mask, __m128i a, __m128i b) {
  return _mm_or_si128(_mm_and_si128(mask, a), _mm_andnot_si128(mask, b));
}

static inline __m128i sk_cpu_estimate_lookup_sse2(const uint32_t* table, __m128i idx) {
  uint32_t i[4];
  _mm_storeu_si128((__m128i*)(void*)i, idx);
  return _mm_setr_epi32((int)table[i[0]], (int)table[i[1]], (int)table[i[2]], (int)table[i[3]]);
}

static inline __m128i sk_cpu_estimate_rcp_sse2(const uint32_t* table, __m128i b) {
  const __m128i sign = _mm_set1_epi32((int)0x80000000u), mant = _mm_set1_epi32(0x7fffff),
                byte = _mm_set1_epi32(0xff);
  __m128i s = _mm_and_si128(b, sign), e = _mm_and_si128(_mm_srli_epi32(b, 23), byte),
          m = _mm_and_si128(b, mant);
  __m128i t = sk_cpu_estimate_lookup_sse2(table, _mm_srli_epi32(m, 23 - SK_CPU_ESTIMATE_BITS));
  __m128i oe = _mm_sub_epi32(_mm_add_epi32(_mm_and_si128(_mm_srli_epi32(t, 23), byte),
                                           _mm_set1_epi32(127)),
                             e);
  __m128i r = _mm_or_si128(_mm_or_si128(s, _mm_slli_epi32(oe, 23)), _mm_and_si128(t, mant));
  r = sk_cpu_estimate_select_sse2(_mm_cmpgt_epi32(oe, _mm_setzero_si128()), r, s);
  r = sk_cpu_estimate_select_sse2(_mm_cmpeq_epi32(e, _mm_setzero_si128()),
                                  _mm_or_si128(s, _mm_set1_epi32(0x7f800000)), r);
  __m128i special = sk_cpu_estimate_select_sse2(_mm_cmpeq_epi32(m, _mm_setzero_si128()), s,
                                                _mm_or_si128(b, _mm_set1_epi32(0x400000)));
  return sk_cpu_estimate_select_sse2(_mm_cmpeq_epi32(e, byte), special, r);
}

static inline __m128i sk_cpu_estimate_rsqrt_sse2(const uint32_t* table, __m128i b) {
  const __m128i sign = _mm_set1_epi32((int)0x80000000u), mant = _mm_set1_epi32(0x7fffff),
                byte = _mm_set1_epi32(0xff), one = _mm_set1_epi32(1),
                dnan = _mm_set1_epi32((int)0xffc00000u), zero = _mm_setzero_si128();
  __m128i s = _mm_and_si128(b, sign), e = _mm_and_si128(_mm_srli_epi32(b, 23), byte),
          m = _mm_and_si128(b, mant);
  __m128i eu = _mm_sub_epi32(e, _mm_set1_epi32(127));
  __m128i p = _mm_and_si128(eu, one);
  __m128i idx = _mm_add_epi32(_mm_slli_epi32(_mm_add_epi32(p, one), SK_CPU_ESTIMATE_BITS),
                              _mm_srli_epi32(m, 23 - SK_CPU_ESTIMATE_BITS));
  __m128i t = sk_cpu_estimate_lookup_sse2(table, idx);
  /* (e - 127 - p) is even, so the arithmetic shift is the scalar's exact / 2. */
  __m128i oe = _mm_sub_epi32(_mm_and_si128(_mm_srli_epi32(t, 23), byte),
                             _mm_srai_epi32(_mm_sub_epi32(eu, p), 1));
  __m128i r = _mm_or_si128(_mm_slli_epi32(oe, 23), _mm_and_si128(t, mant));
  r = sk_cpu_estimate_select_sse2(_mm_cmpeq_epi32(s, zero), r, dnan);
  r = sk_cpu_estimate_select_sse2(_mm_cmpeq_epi32(e, zero),
                                  _mm_or_si128(s, _mm_set1_epi32(0x7f800000)), r);
  __m128i inf = sk_cpu_estimate_select_sse2(_mm_cmpeq_epi32(s, zero), zero, dnan);
  __m128i special = sk_cpu_estimate_select_sse2(_mm_cmpeq_epi32(m, zero), inf,
                                                _mm_or_si128(b, _mm_set1_epi32(0x400000)));
  return sk_cpu_estimate_select_sse2(_mm_cmpeq_epi32(e, byte), special, r);
}
#endif

#if defined(__AVX2__)
#include <immintrin.h>

static inline __m256i sk_cpu_estimate_rcp_avx2(const uint32_t* table, __m256i b) {
  const __m256i mant = _mm256_set1_epi32(0x7fffff), byte = _mm256_set1_epi32(0xff),
                zero = _mm256_setzero_si256();
  __m256i s = _mm256_and_si256(b, _mm256_set1_epi32((int)0x80000000u)),
          e = _mm256_and_si256(_mm256_srli_epi32(b, 23), byte), m = _mm256_and_si256(b, mant);
  __m256i t = _mm256_i32gather_epi32((const int*)table,
                                     _mm256_srli_epi32(m, 23 - SK_CPU_ESTIMATE_BITS), 4);
  __m256i oe = _mm256_sub_epi32(_mm256_add_epi32(_mm256_and_si256(_mm256_srli_epi32(t, 23), byte),
                                                 _mm256_set1_epi32(127)),
                                e);
  __m256i r = _mm256_or_si256(_mm256_or_si256(s, _mm256_slli_epi32(oe, 23)),
                              _mm256_and_si256(t, mant));
  r = _mm256_blendv_epi8(s, r, _mm256_cmpgt_epi32(oe, zero));
  r = _mm256_blendv_epi8(r, _mm256_or_si256(s, _mm256_set1_epi32(0x7f800000)),
                         _mm256_cmpeq_epi32(e, zero));
  __m256i special = _mm256_blendv_epi8(_mm256_or_si256(b, _mm256_set1_epi32(0x400000)), s,
                                       _mm256_cmpeq_epi32(m, zero));
  return _mm256_blendv_epi8(r, special, _mm256_cmpeq_epi32(e, byte));
}

static inline __m256i sk_cpu_estimate_rsqrt_avx2(const uint32_t* table, __m256i b) {
  const __m256i mant = _mm256_set1_epi32(0x7fffff), byte = _mm256_set1_epi32(0xff),
                one = _mm256_set1_epi32(1), dnan = _mm256_set1_epi32((int)0xffc00000u),
                zero = _mm256_setzero_si256();
  __m256i s = _mm256_and_si256(b, _mm256_set1_epi32((int)0x80000000u)),
          e = _mm256_and_si256(_mm256_srli_epi32(b, 23), byte), m = _mm256_and_si256(b, mant);
  __m256i eu = _mm256_sub_epi32(e, _mm256_set1_epi32(127));
  __m256i p = _mm256_and_si256(eu, one);
  __m256i idx = _mm256_add_epi32(_mm256_slli_epi32(_mm256_add_epi32(p, one), SK_CPU_ESTIMATE_BITS),
                                 _mm256_srli_epi32(m, 23 - SK_CPU_ESTIMATE_BITS));
  __m256i t = _mm256_i32gather_epi32((const int*)table, idx, 4);
  __m256i oe = _mm256_sub_epi32(_mm256_and_si256(_mm256_srli_epi32(t, 23), byte),
                                _mm256_srai_epi32(_mm256_sub_epi32(eu, p), 1));
  __m256i r = _mm256_or_si256(_mm256_slli_epi32(oe, 23), _mm256_and_si256(t, mant));
  __m256i positive = _mm256_cmpeq_epi32(s, zero);
  r = _mm256_blendv_epi8(dnan, r, positive);
  r = _mm256_blendv_epi8(r, _mm256_or_si256(s, _mm256_set1_epi32(0x7f800000)),
                         _mm256_cmpeq_epi32(e, zero));
  __m256i inf = _mm256_blendv_epi8(dnan, zero, positive);
  __m256i special = _mm256_blendv_epi8(_mm256_or_si256(b, _mm256_set1_epi32(0x400000)), inf,
                                       _mm256_cmpeq_epi32(m, zero));
  return _mm256_blendv_epi8(r, special, _mm256_cmpeq_epi32(e, byte));
}
#endif

#ifdef __cplusplus
/* The recorded table of the vendor general.cpu_identity names, or
 * nullptr when the native instruction already gives that vendor's bits: the
 * pref is 0, or names the CPU this runs on (SkCpuEstimates_mozilla.cpp). */
const uint32_t* sk_cpu_estimates();

/* The same, resolved once when SkOpts initialises (the moment the opts tiers
 * are chosen too), for the raster pipeline: an inline load instead of a call,
 * which would make every caller spill its vector registers and cost the
 * native path time that stock Firefox does not spend. */
extern const uint32_t* gSkCpuEstimatesForPipeline;
void sk_cpu_estimates_init_pipeline();
static inline const uint32_t* sk_cpu_estimates_cached() { return gSkCpuEstimatesForPipeline; }

/* Whether general.cpu_identity names an ARM64 machine on this x86-64 one:
 * the opts tiers then switch to Skia's AArch64 code, built against
 * SkNeonEmu.h (the _neonemu.cpp files). */
bool sk_cpu_emulates_arm64();
#endif

#endif
