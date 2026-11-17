/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/* celt_neonemu.c built for AVX2 and FMA (media/libopus/moz.build): its fused
 * multiply-adds are one instruction instead of a libm call, with the same
 * bits. The baseline build's kernels hand over here when
 * celt_neonemu_use_fma() (x86cpu.c) says the CPU has both. */

#define CELT_NEONEMU_FMA_BUILD 1
#define celt_inner_prod_neonemu celt_inner_prod_neonemu_fma
#define dual_inner_prod_neonemu dual_inner_prod_neonemu_fma
#define celt_pitch_xcorr_neonemu celt_pitch_xcorr_neonemu_fma
#define comb_filter_const_neonemu comb_filter_const_neonemu_fma
#define celt_deemphasis_neonemu celt_deemphasis_neonemu_fma
#define deemphasis_stereo_simple_neonemu deemphasis_stereo_simple_neonemu_fma

#include "celt_neonemu.c"
