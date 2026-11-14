/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// SkNeonEmu.h's float operations on 8 lanes at once, for Skia's raster
// pipeline at AVX2's width with the AArch64 helpers (SKRP_ARM_SEMANTICS in
// SkRasterPipeline_opts.h). Each gives every lane what the 4-lane function
// gives it: the x86 instruction when every lane is one both ISAs define alike,
// the Arm NaN and infinity rules as vector selects when a lane is a NaN or an
// infinity, and the 4-lane function on each half for the rare rest (estimates
// of subnormals or near the exponent limits, conversions out of range).
// browser/tests/neon-emu compares each with the 4-lane function on both halves.

#ifndef SkNeonEmuWide_DEFINED
#define SkNeonEmuWide_DEFINED

#if NEON_EMU_FAST

NEON_EMU_SI float32x4_t neon_emu_lo8(__m256 v) { return (float32x4_t)_mm256_castps256_ps128(v); }
NEON_EMU_SI float32x4_t neon_emu_hi8(__m256 v) { return (float32x4_t)_mm256_extractf128_ps(v, 1); }
NEON_EMU_SI __m256 neon_emu_join8(float32x4_t lo, float32x4_t hi) {
  return _mm256_insertf128_ps(_mm256_castps128_ps256((__m128)lo), (__m128)hi, 1);
}
NEON_EMU_SI __m256i neon_emu_join8i(__m128i lo, __m128i hi) {
  return _mm256_inserti128_si256(_mm256_castsi128_si256(lo), hi, 1);
}

NEON_EMU_SI int neon_emu_any_nan8(__m256 v) {
  return _mm256_movemask_ps(_mm256_cmp_ps(v, v, _CMP_UNORD_Q));
}
NEON_EMU_SI int neon_emu_all8(__m256i m) {
  return _mm256_movemask_ps(_mm256_castsi256_ps(m)) == 0xff;
}
NEON_EMU_SI __m256i neon_emu_sel8(__m256i m, __m256i a, __m256i b) {
  return _mm256_blendv_epi8(b, a, m);  // m ? a : b
}
NEON_EMU_SI __m256i neon_emu_exp8(__m256i u) {
  return _mm256_and_si256(_mm256_srli_epi32(u, 23), _mm256_set1_epi32(0xff));
}
NEON_EMU_SI __m256i neon_emu_within8(__m256i x, int lo, int hi) {
  return _mm256_andnot_si256(_mm256_or_si256(_mm256_cmpgt_epi32(_mm256_set1_epi32(lo), x),
                                             _mm256_cmpgt_epi32(x, _mm256_set1_epi32(hi))),
                             _mm256_set1_epi32(-1));
}
NEON_EMU_SI __m256i neon_emu_isnan8i(__m256i u) {
  return _mm256_cmpgt_epi32(_mm256_and_si256(u, _mm256_set1_epi32(0x7fffffff)),
                            _mm256_set1_epi32(0x7f800000));
}
NEON_EMU_SI __m256i neon_emu_issnan8i(__m256i u) {
  const __m256i q = _mm256_set1_epi32(0x400000);
  return _mm256_andnot_si256(_mm256_cmpeq_epi32(_mm256_and_si256(u, q), q), neon_emu_isnan8i(u));
}
// neon_emu_nans_v on 8 lanes.
NEON_EMU_SI __m256i neon_emu_nans8(__m256i x, __m256i y, __m256i z, __m256i* any) {
  const __m256i q = _mm256_set1_epi32(0x400000);
  __m256i nx = neon_emu_isnan8i(x), ny = neon_emu_isnan8i(y), nz = neon_emu_isnan8i(z);
  *any = _mm256_or_si256(nx, _mm256_or_si256(ny, nz));
  __m256i r = z;
  r = neon_emu_sel8(ny, y, r);
  r = neon_emu_sel8(nx, x, r);
  r = neon_emu_sel8(neon_emu_issnan8i(z), _mm256_or_si256(z, q), r);
  r = neon_emu_sel8(neon_emu_issnan8i(y), _mm256_or_si256(y, q), r);
  r = neon_emu_sel8(neon_emu_issnan8i(x), _mm256_or_si256(x, q), r);
  return r;
}
// The same for two operands: four selects instead of six.
NEON_EMU_SI __m256i neon_emu_nans8_2(__m256i x, __m256i y, __m256i* any) {
  const __m256i q = _mm256_set1_epi32(0x400000);
  __m256i nx = neon_emu_isnan8i(x), ny = neon_emu_isnan8i(y);
  *any = _mm256_or_si256(nx, ny);
  __m256i r = neon_emu_sel8(nx, x, y);
  r = neon_emu_sel8(neon_emu_issnan8i(y), _mm256_or_si256(y, q), r);
  r = neon_emu_sel8(neon_emu_issnan8i(x), _mm256_or_si256(x, q), r);
  return r;
}
NEON_EMU_SI __m256i neon_emu_infzero8(__m256i x, __m256i y) {
  const __m256i abs = _mm256_set1_epi32(0x7fffffff), inf = _mm256_set1_epi32(0x7f800000),
                zero = _mm256_setzero_si256();
  __m256i ax = _mm256_and_si256(x, abs), ay = _mm256_and_si256(y, abs);
  return _mm256_or_si256(_mm256_and_si256(_mm256_cmpeq_epi32(ax, inf), _mm256_cmpeq_epi32(ay, zero)),
                         _mm256_and_si256(_mm256_cmpeq_epi32(ax, zero), _mm256_cmpeq_epi32(ay, inf)));
}
NEON_EMU_SI __m256 neon_emu_nan_rules8(__m256 r, __m256i prop, __m256i any) {
  __m256i out = neon_emu_sel8(_mm256_castps_si256(_mm256_cmp_ps(r, r, _CMP_UNORD_Q)),
                              _mm256_set1_epi32(0x7fc00000), _mm256_castps_si256(r));
  return _mm256_castsi256_ps(neon_emu_sel8(any, prop, out));
}

// The rare paths (the 4-lane fallbacks for subnormal and out-of-range lanes)
// are out of line and cold. The NaN lanes Skia's blends make routinely
// (clip_color's 0/0) are handled inline: a call there cost the non-separable
// modes 20-35% (PR #40, an AMD runner, against inline). Only lanes with two or
// more NaN operands, which those blends do not make, call the full rules.
#define NEON_EMU_COLD static __attribute__((noinline, cold, unused))

// FMLA: addend + op1*op2 (neon_emu_fma_v).
NEON_EMU_COLD __m256 neon_emu_fma8_nan_full(__m256 r, __m256 addend, __m256 op1, __m256 op2) {
  __m256i a = _mm256_castps_si256(addend), b = _mm256_castps_si256(op1), c = _mm256_castps_si256(op2), any;
  __m256i prop = neon_emu_nans8(a, b, c, &any);
  __m256 out = neon_emu_nan_rules8(r, prop, any);
  __m256i qnan_addend = _mm256_andnot_si256(neon_emu_issnan8i(a), neon_emu_isnan8i(a));
  return _mm256_castsi256_ps(neon_emu_sel8(_mm256_and_si256(qnan_addend, neon_emu_infzero8(b, c)),
                                           _mm256_set1_epi32(0x7fc00000), _mm256_castps_si256(out)));
}
// The NaN lanes Skia's blends make (clip_color's l * 1/0 fed to a mad) carry
// at most one NaN operand, or none. One NaN operand gives that operand
// quieted; it is taken from the operand, not from r, because the compiler
// folds FMLS's negation into VFNMADD, which returns an operand NaN unnegated.
// A NaN made from numbers is Arm's default NaN (x86's is negative), and a
// quiet NaN addend with infinity times zero gives it too. A lane with two or
// more NaN operands, where priorities decide, takes the full rules, out of line.
NEON_EMU_SI __m256 neon_emu_fma8_nan(__m256 r, __m256 addend, __m256 op1, __m256 op2) {
  __m256 na = _mm256_cmp_ps(addend, addend, _CMP_UNORD_Q), nb = _mm256_cmp_ps(op1, op1, _CMP_UNORD_Q),
         nc = _mm256_cmp_ps(op2, op2, _CMP_UNORD_Q);
  __m256 multi = _mm256_or_ps(_mm256_and_ps(na, nb), _mm256_and_ps(_mm256_or_ps(na, nb), nc));
  if (__builtin_expect(_mm256_movemask_ps(multi) != 0, 0)) return neon_emu_fma8_nan_full(r, addend, op1, op2);
  __m256 in = _mm256_or_ps(_mm256_or_ps(na, nb), nc);
  __m256 one = _mm256_or_ps(_mm256_blendv_ps(_mm256_blendv_ps(op2, op1, nb), addend, na),
                            _mm256_castsi256_ps(_mm256_set1_epi32(0x400000)));
  __m256 made = _mm256_andnot_ps(in, _mm256_cmp_ps(r, r, _CMP_UNORD_Q));
  __m256i out = neon_emu_sel8(_mm256_castps_si256(made), _mm256_set1_epi32(0x7fc00000), _mm256_castps_si256(r));
  out = neon_emu_sel8(_mm256_castps_si256(in), _mm256_castps_si256(one), out);
  if (_mm256_movemask_ps(na)) {
    __m256i a = _mm256_castps_si256(addend);
    __m256i qnan_addend = _mm256_andnot_si256(neon_emu_issnan8i(a), neon_emu_isnan8i(a));
    out = neon_emu_sel8(_mm256_and_si256(qnan_addend,
                                         neon_emu_infzero8(_mm256_castps_si256(op1), _mm256_castps_si256(op2))),
                        _mm256_set1_epi32(0x7fc00000), out);
  }
  return _mm256_castsi256_ps(out);
}
NEON_EMU_SI __m256 neon_emu_fma8(__m256 addend, __m256 op1, __m256 op2) {
  __m256 r = _mm256_fmadd_ps(op1, op2, addend);
  if (__builtin_expect(!neon_emu_any_nan8(r), 1)) return r;
  return neon_emu_fma8_nan(r, addend, op1, op2);
}
// FMLS: op1 negated first, a NaN's sign included.
NEON_EMU_SI __m256 neon_emu_fms8(__m256 addend, __m256 op1, __m256 op2) {
  return neon_emu_fma8(addend, _mm256_xor_ps(op1, _mm256_castsi256_ps(_mm256_set1_epi32((int)0x80000000u))), op2);
}
// FMIN / FMAX: equal lanes (+0 and -0) take the sign rule; NaN lanes FPProcessNaNs.
// A lane with one NaN operand gives that NaN quieted, whichever it is; only a
// lane with two takes the priority rules.
NEON_EMU_COLD __m256 neon_emu_minmax8_nan_full(__m256 r, __m256 x, __m256 y) {
  __m256i any, prop = neon_emu_nans8_2(_mm256_castps_si256(x), _mm256_castps_si256(y), &any);
  return _mm256_castsi256_ps(neon_emu_sel8(any, prop, _mm256_castps_si256(r)));
}
NEON_EMU_SI __m256 neon_emu_minmax8_nan(__m256 r, __m256 x, __m256 y) {
  __m256 nx = _mm256_cmp_ps(x, x, _CMP_UNORD_Q), ny = _mm256_cmp_ps(y, y, _CMP_UNORD_Q);
  if (__builtin_expect(_mm256_movemask_ps(_mm256_and_ps(nx, ny)) != 0, 0)) {
    return neon_emu_minmax8_nan_full(r, x, y);
  }
  __m256 nan = _mm256_or_ps(_mm256_blendv_ps(y, x, nx), _mm256_castsi256_ps(_mm256_set1_epi32(0x400000)));
  return _mm256_blendv_ps(r, nan, _mm256_or_ps(nx, ny));
}
NEON_EMU_SI __m256 neon_emu_min8_nan(__m256 r, __m256 x, __m256 y) { return neon_emu_minmax8_nan(r, x, y); }
NEON_EMU_SI __m256 neon_emu_min8(__m256 x, __m256 y) {
  __m256 r = _mm256_blendv_ps(_mm256_min_ps(x, y), _mm256_or_ps(x, y), _mm256_cmp_ps(x, y, _CMP_EQ_OQ));
  if (__builtin_expect(!_mm256_movemask_ps(_mm256_cmp_ps(x, y, _CMP_UNORD_Q)), 1)) return r;
  return neon_emu_min8_nan(r, x, y);
}
NEON_EMU_SI __m256 neon_emu_max8_nan(__m256 r, __m256 x, __m256 y) { return neon_emu_minmax8_nan(r, x, y); }
NEON_EMU_SI __m256 neon_emu_max8(__m256 x, __m256 y) {
  __m256 r = _mm256_blendv_ps(_mm256_max_ps(x, y), _mm256_and_ps(x, y), _mm256_cmp_ps(x, y, _CMP_EQ_OQ));
  if (__builtin_expect(!_mm256_movemask_ps(_mm256_cmp_ps(x, y, _CMP_UNORD_Q)), 1)) return r;
  return neon_emu_max8_nan(r, x, y);
}
NEON_EMU_SI __m256 neon_emu_abs8(__m256 x) {
  return _mm256_and_ps(x, _mm256_castsi256_ps(_mm256_set1_epi32(0x7fffffff)));
}
// FRINTM / FRINTP: a NaN comes back quieted, as ROUNDPS gives it.
NEON_EMU_SI __m256 neon_emu_floor8(__m256 x) { return _mm256_floor_ps(x); }
NEON_EMU_SI __m256 neon_emu_ceil8(__m256 x) { return _mm256_ceil_ps(x); }
NEON_EMU_COLD __m256 neon_emu_sqrt8_slow(__m256 x) {
  return neon_emu_join8(vsqrtq_f32(neon_emu_lo8(x)), vsqrtq_f32(neon_emu_hi8(x)));
}
NEON_EMU_SI __m256 neon_emu_sqrt8(__m256 x) {
  if (!_mm256_movemask_ps(_mm256_or_ps(_mm256_cmp_ps(x, x, _CMP_UNORD_Q),
                                       _mm256_cmp_ps(x, _mm256_setzero_ps(), _CMP_LT_OQ)))) {
    return _mm256_sqrt_ps(x);
  }
  return neon_emu_sqrt8_slow(x);
}

// FRECPE / FRSQRTE: the table, for normal inputs whose result is normal.
NEON_EMU_COLD __m256 neon_emu_recpe8_slow(__m256 a) {
  return neon_emu_join8(vrecpeq_f32(neon_emu_lo8(a)), vrecpeq_f32(neon_emu_hi8(a)));
}
NEON_EMU_COLD __m256 neon_emu_rsqrte8_slow(__m256 a) {
  return neon_emu_join8(vrsqrteq_f32(neon_emu_lo8(a)), vrsqrteq_f32(neon_emu_hi8(a)));
}
NEON_EMU_SI __m256i neon_emu_recpe8_normal(__m256i u, __m256i e) {
  __m256i f = _mm256_i32gather_epi32((const int*)kNeonEmuEstimateWords.recip,
                                     _mm256_srli_epi32(_mm256_and_si256(u, _mm256_set1_epi32(0x7fffff)), 15), 4);
  __m256i re = _mm256_slli_epi32(_mm256_sub_epi32(_mm256_set1_epi32(253), e), 23);
  __m256i sign = _mm256_and_si256(u, _mm256_set1_epi32((int)0x80000000u));
  return _mm256_or_si256(_mm256_or_si256(sign, re), f);
}
// +-0 gives +-infinity, a select: Skia's blends take the reciprocal of zero on
// every pixel of a grey layer (set_sat's sat, clip_color's l - mn), and the
// 4-lane fallback there cost the non-separable modes several times native.
NEON_EMU_SI __m256 neon_emu_recpe8(__m256 a) {
  __m256i u = _mm256_castps_si256(a), e = neon_emu_exp8(u);
  __m256i ok = neon_emu_within8(e, 1, 252);
  if (neon_emu_all8(ok)) return _mm256_castsi256_ps(neon_emu_recpe8_normal(u, e));
  __m256i zero = _mm256_cmpeq_epi32(_mm256_and_si256(u, _mm256_set1_epi32(0x7fffffff)), _mm256_setzero_si256());
  if (neon_emu_all8(_mm256_or_si256(ok, zero))) {
    __m256i inf = _mm256_or_si256(_mm256_and_si256(u, _mm256_set1_epi32((int)0x80000000u)),
                                  _mm256_set1_epi32(0x7f800000));
    return _mm256_castsi256_ps(neon_emu_sel8(zero, inf, neon_emu_recpe8_normal(u, e)));
  }
  return neon_emu_recpe8_slow(a);
}
NEON_EMU_SI __m256 neon_emu_rsqrte8(__m256 a) {
  __m256i u = _mm256_castps_si256(a), e = neon_emu_exp8(u);
  if (neon_emu_all8(_mm256_and_si256(neon_emu_within8(e, 1, 254),
                                     _mm256_cmpgt_epi32(u, _mm256_set1_epi32(-1))))) {
    __m256i m = _mm256_and_si256(u, _mm256_set1_epi32(0x7fffff));
    __m256i odd = _mm256_cmpeq_epi32(_mm256_and_si256(e, _mm256_set1_epi32(1)), _mm256_set1_epi32(1));
    __m256i idx = _mm256_blendv_epi8(_mm256_add_epi32(_mm256_srli_epi32(m, 15), _mm256_set1_epi32(128)),
                                     _mm256_srli_epi32(m, 16), odd);
    __m256i f = _mm256_i32gather_epi32((const int*)kNeonEmuEstimateWords.rsqrt, idx, 4);
    __m256i re = _mm256_slli_epi32(_mm256_srli_epi32(_mm256_sub_epi32(_mm256_set1_epi32(380), e), 1), 23);
    return _mm256_castsi256_ps(_mm256_or_si256(re, f));
  }
  return neon_emu_rsqrte8_slow(a);
}
// FRECPS: 2 - a*b rounded once; FRSQRTS: (3 - a*b) / 2 (see vrecpsq_f32).
NEON_EMU_SI __m256 neon_emu_recps8_nan(__m256 r0, __m256 a, __m256 b) {
  __m256i na = _mm256_xor_si256(_mm256_castps_si256(a), _mm256_set1_epi32((int)0x80000000u)),
          ub = _mm256_castps_si256(b), any;
  __m256i prop = neon_emu_nans8_2(na, ub, &any);
  __m256i r = neon_emu_sel8(neon_emu_infzero8(na, ub), _mm256_set1_epi32(0x40000000), _mm256_castps_si256(r0));
  return _mm256_castsi256_ps(neon_emu_sel8(any, prop, r));
}
NEON_EMU_SI __m256 neon_emu_recps8(__m256 a, __m256 b) {
  __m256 r0 = _mm256_fnmadd_ps(a, b, _mm256_set1_ps(2.0f));
  __m256 n = _mm256_cmp_ps(r0, r0, _CMP_UNORD_Q);
  if (__builtin_expect(!_mm256_movemask_ps(n), 1)) return r0;
  // With no NaN operand the NaN lanes are infinity times zero (2 - inf is
  // -inf): FRECPS gives 2.0 there. rcp_approx(0) takes this every time.
  if (!_mm256_movemask_ps(_mm256_cmp_ps(a, b, _CMP_UNORD_Q))) return _mm256_blendv_ps(r0, _mm256_set1_ps(2.0f), n);
  return neon_emu_recps8_nan(r0, a, b);
}
NEON_EMU_COLD __m256 neon_emu_rsqrts8_slow(__m256 a, __m256 b) {
  __m256i ua = _mm256_castps_si256(a), ub = _mm256_castps_si256(b);
  __m256i ea = neon_emu_exp8(ua), eb = neon_emu_exp8(ub), ff = _mm256_set1_epi32(0xff);
  __m256i special = _mm256_or_si256(_mm256_cmpeq_epi32(ea, ff), _mm256_cmpeq_epi32(eb, ff));
  __m256i ok = _mm256_or_si256(special, neon_emu_within8(_mm256_add_epi32(ea, eb), 0, 379));
  if (!neon_emu_all8(ok)) {
    return neon_emu_join8(vrsqrtsq_f32(neon_emu_lo8(a), neon_emu_lo8(b)),
                          vrsqrtsq_f32(neon_emu_hi8(a), neon_emu_hi8(b)));
  }
  __m256 r0 = _mm256_fnmadd_ps(a, b, _mm256_set1_ps(3.0f));
  __m256 half = _mm256_mul_ps(r0, _mm256_set1_ps(0.5f));
  if (!neon_emu_any_nan8(r0)) return half;
  __m256i na = _mm256_xor_si256(ua, _mm256_set1_epi32((int)0x80000000u)), any;
  __m256i prop = neon_emu_nans8(na, ub, ub, &any);
  __m256i r = neon_emu_sel8(neon_emu_infzero8(na, ub), _mm256_set1_epi32(0x3fc00000), _mm256_castps_si256(half));
  return _mm256_castsi256_ps(neon_emu_sel8(any, prop, r));
}
// The common case first: biased exponents summing to 379 or less (a*b well
// below overflow; an infinity times a small finite stays an exact infinity),
// and no NaN made.
NEON_EMU_SI __m256 neon_emu_rsqrts8(__m256 a, __m256 b) {
  __m256i e = _mm256_add_epi32(neon_emu_exp8(_mm256_castps_si256(a)), neon_emu_exp8(_mm256_castps_si256(b)));
  __m256 r0 = _mm256_fnmadd_ps(a, b, _mm256_set1_ps(3.0f));
  __m256i bad = _mm256_or_si256(_mm256_cmpgt_epi32(e, _mm256_set1_epi32(379)),
                                _mm256_castps_si256(_mm256_cmp_ps(r0, r0, _CMP_UNORD_Q)));
  if (__builtin_expect(_mm256_testz_si256(bad, bad), 1)) return _mm256_mul_ps(r0, _mm256_set1_ps(0.5f));
  return neon_emu_rsqrts8_slow(a, b);
}

// FCVTNS / FCVTNU: CVTPS2DQ (round to nearest even) for lanes in range.
NEON_EMU_COLD __m256i neon_emu_cvtns8_slow(__m256 x) {
  return neon_emu_join8i((__m128i)vcvtnq_s32_f32(neon_emu_lo8(x)), (__m128i)vcvtnq_s32_f32(neon_emu_hi8(x)));
}
NEON_EMU_SI __m256i neon_emu_cvtns8(__m256 x) {
  if (_mm256_movemask_ps(_mm256_and_ps(_mm256_cmp_ps(x, _mm256_set1_ps(-2147483648.0f), _CMP_GE_OQ),
                                       _mm256_cmp_ps(x, _mm256_set1_ps(2147483648.0f), _CMP_LT_OQ))) == 0xff) {
    return _mm256_cvtps_epi32(x);
  }
  return neon_emu_cvtns8_slow(x);
}
NEON_EMU_COLD __m256i neon_emu_cvtnu8_slow(__m256 x) {
  return neon_emu_join8i((__m128i)vcvtnq_u32_f32(neon_emu_lo8(x)), (__m128i)vcvtnq_u32_f32(neon_emu_hi8(x)));
}
NEON_EMU_SI __m256i neon_emu_cvtnu8(__m256 x) {
  if (_mm256_movemask_ps(_mm256_and_ps(_mm256_cmp_ps(x, _mm256_setzero_ps(), _CMP_GE_OQ),
                                       _mm256_cmp_ps(x, _mm256_set1_ps(2147483648.0f), _CMP_LT_OQ))) == 0xff) {
    return _mm256_cvtps_epi32(x);
  }
  return neon_emu_cvtnu8_slow(x);
}

#undef NEON_EMU_COLD
#endif  // NEON_EMU_FAST
#endif  // SkNeonEmuWide_DEFINED
