/* Throwaway: RCPPS-as-another-vendor lookups, gather vs scalar loads, on this CPU.
 * Built with the shipped SkCpuEstimates.h; the table contents do not matter for speed. */
#include <immintrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "src/opts/SkCpuEstimates.h"

uint32_t table[SK_CPU_ESTIMATE_TABLE_SIZE];

#define FAST_BODY(LOOKUP)                                                                       \
  const __m256i expo = _mm256_set1_epi32(0x7f800000);                                           \
  __m256i x = _mm256_and_si256(b, expo);                                                        \
  __m256i idx = _mm256_and_si256(_mm256_srli_epi32(b, 23 - SK_CPU_ESTIMATE_BITS),               \
                                 _mm256_set1_epi32(SK_CPU_ESTIMATE_ENTRIES - 1));               \
  __m256i t = LOOKUP;                                                                           \
  __m256i r = _mm256_add_epi32(_mm256_sub_epi32(t, x), _mm256_set1_epi32(127 << 23));           \
  r = _mm256_blendv_epi8(r, expo, _mm256_cmpeq_epi32(x, _mm256_setzero_si256()));               \
  return _mm256_or_si256(r, _mm256_andnot_si256(_mm256_set1_epi32(0x7fffffff), b));

static inline __m256i v_gather(__m256i b) {
  FAST_BODY(_mm256_i32gather_epi32((const int*)table, idx, 4))
}
static inline __m256i lookup_mem(__m256i idx) {
  uint32_t i[8] __attribute__((aligned(32)));
  _mm256_store_si256((__m256i*)i, idx);
  return _mm256_setr_epi32(table[i[0]], table[i[1]], table[i[2]], table[i[3]], table[i[4]],
                           table[i[5]], table[i[6]], table[i[7]]);
}
static inline __m256i v_mem(__m256i b) { FAST_BODY(lookup_mem(idx)) }
static inline __m256i lookup_ext(__m256i idx) {
  __m128i lo = _mm256_castsi256_si128(idx), hi = _mm256_extracti128_si256(idx, 1);
  uint64_t a = (uint64_t)_mm_cvtsi128_si64(lo), c = (uint64_t)_mm_extract_epi64(lo, 1),
           d = (uint64_t)_mm_cvtsi128_si64(hi), e = (uint64_t)_mm_extract_epi64(hi, 1);
  __m128i l = _mm_cvtsi32_si128((int)table[(uint32_t)a]);
  l = _mm_insert_epi32(l, (int)table[a >> 32], 1);
  l = _mm_insert_epi32(l, (int)table[(uint32_t)c], 2);
  l = _mm_insert_epi32(l, (int)table[c >> 32], 3);
  __m128i h = _mm_cvtsi32_si128((int)table[(uint32_t)d]);
  h = _mm_insert_epi32(h, (int)table[d >> 32], 1);
  h = _mm_insert_epi32(h, (int)table[(uint32_t)e], 2);
  h = _mm_insert_epi32(h, (int)table[e >> 32], 3);
  return _mm256_inserti128_si256(_mm256_castsi128_si256(l), h, 1);
}
static inline __m256i v_ext(__m256i b) { FAST_BODY(lookup_ext(idx)) }
static inline __m256i v_native(__m256i b) {
  return _mm256_castps_si256(_mm256_rcp_ps(_mm256_castsi256_ps(b)));
}

#define N (1 << 16)
static float in[N] __attribute__((aligned(32)));
float out[N] __attribute__((aligned(32)));

static double now(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts.tv_sec * 1e9 + ts.tv_nsec;
}

/* Throughput: independent vectors, with some float work around each lookup
 * as in a blend stage (a dodge channel is ~10 ops per rcp). */
#define BENCH(name, F)                                                                         \
  static double bench_##name(void) {                                                           \
    double best = 1e30;                                                                        \
    for (int rep = 0; rep < 15; rep++) {                                                       \
      double t0 = now();                                                                       \
      for (int k = 0; k < 20; k++) {                                                           \
        for (int i = 0; i < N; i += 8) {                                                       \
          __m256 v = _mm256_load_ps(in + i);                                                   \
          __m256 s = _mm256_fmadd_ps(v, v, _mm256_set1_ps(0.25f));                             \
          __m256 e = _mm256_castsi256_ps(F(_mm256_castps_si256(s)));                           \
          __m256 y = _mm256_mul_ps(_mm256_min_ps(_mm256_mul_ps(e, v), s), v);                  \
          y = _mm256_fmadd_ps(y, s, _mm256_sub_ps(v, s));                                      \
          _mm256_store_ps(out + i, y);                                                         \
        }                                                                                      \
        __asm__ volatile("" : : "r"(out) : "memory");                                          \
      }                                                                                        \
      double t = (now() - t0) / (20.0 * N / 8);                                                \
      best = t < best ? t : best;                                                              \
    }                                                                                          \
    return best;                                                                               \
  }
BENCH(native, v_native)
BENCH(gather, v_gather)
BENCH(mem, v_mem)
BENCH(ext, v_ext)

int main(void) {
  srand(1);
  for (int i = 0; i < SK_CPU_ESTIMATE_TABLE_SIZE; i++) table[i] = 0x3f000000u | (uint32_t)(rand() & 0x7fffff);
  for (int i = 0; i < N; i++) in[i] = 0.05f + (float)rand() / RAND_MAX;
  /* The three lookups must agree. */
  for (int i = 0; i < N; i += 8) {
    __m256i b = _mm256_castps_si256(_mm256_load_ps(in + i));
    __m256i g = v_gather(b), m = v_mem(b), x = v_ext(b);
    if (!_mm256_testc_si256(_mm256_cmpeq_epi32(g, m), _mm256_set1_epi32(-1)) ||
        !_mm256_testc_si256(_mm256_cmpeq_epi32(g, x), _mm256_set1_epi32(-1))) {
      printf("MISMATCH at %d\n", i);
      return 1;
    }
  }
  double n = bench_native(), g = bench_gather(), m = bench_mem(), x = bench_ext();
  double sum = 0;
  for (int i = 0; i < N; i++) sum += out[i];
  printf("checksum %g\n", sum);
  printf("ns per 8 lanes: native %.2f  gather %.2f  mem %.2f  ext %.2f\n", n, g, m, x);
  printf("vs native:      gather %.2fx  mem %.2fx  ext %.2fx\n", g / n, m / n, x / n);
  return 0;
}
