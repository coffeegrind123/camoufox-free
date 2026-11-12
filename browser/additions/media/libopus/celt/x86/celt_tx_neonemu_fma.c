/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/* celt_tx_neonemu.c built for AVX2 and FMA (media/libopus/moz.build): its fused
 * multiply-adds are one instruction instead of a libm call, with the same
 * bits. The baseline build's kernels hand over here when
 * celt_neonemu_use_fma() (x86cpu.c) says the CPU has both. */

#define CELT_NEONEMU_FMA_BUILD 1
#define celt_tx_fft4_fwd_float_neonemu celt_tx_fft4_fwd_float_neonemu_fma
#define celt_tx_fft8_ns_float_neonemu celt_tx_fft8_ns_float_neonemu_fma
#define celt_tx_fft16_ns_float_neonemu celt_tx_fft16_ns_float_neonemu_fma
#define celt_tx_fft_pfa_15xM_ns_float_neonemu celt_tx_fft_pfa_15xM_ns_float_neonemu_fma
#define celt_tx_mdct_inv_float_neonemu celt_tx_mdct_inv_float_neonemu_fma
#define celt_tx_fft32_ns_float_neonemu celt_tx_fft32_ns_float_neonemu_fma
#define celt_tx_fft_sr_ns_float_neonemu celt_tx_fft_sr_ns_float_neonemu_fma

#include "celt_tx_neonemu.c"
