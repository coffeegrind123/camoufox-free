/*
 * tx_float_neonemu.c built for AVX2 and FMA (x86/moz.build), so its fused
 * multiply-adds are one instruction instead of a libm call; tx.c chooses this
 * list over the baseline one on such a CPU. Both compute the same bits: fmaf
 * rounds once either way.
 *
 * This file is part of FFmpeg's ffvpx copy in Gecko, under the LGPL 2.1 or
 * later; see tx_float_neonemu.c.
 */

#define ff_tx_codelet_list_float_neonemu ff_tx_codelet_list_float_neonemu_fma
#define ff_tx_fft2_float_neonemu ff_tx_fft2_float_neonemu_fma
#define ff_tx_fft4_fwd_float_neonemu ff_tx_fft4_fwd_float_neonemu_fma
#define ff_tx_fft4_inv_float_neonemu ff_tx_fft4_inv_float_neonemu_fma
#define ff_tx_fft8_float_neonemu ff_tx_fft8_float_neonemu_fma
#define ff_tx_fft8_ns_float_neonemu ff_tx_fft8_ns_float_neonemu_fma
#define ff_tx_fft16_float_neonemu ff_tx_fft16_float_neonemu_fma
#define ff_tx_fft16_ns_float_neonemu ff_tx_fft16_ns_float_neonemu_fma
#define ff_tx_fft32_float_neonemu ff_tx_fft32_float_neonemu_fma
#define ff_tx_fft32_ns_float_neonemu ff_tx_fft32_ns_float_neonemu_fma
#define ff_tx_fft_sr_float_neonemu ff_tx_fft_sr_float_neonemu_fma
#define ff_tx_fft_sr_ns_float_neonemu ff_tx_fft_sr_ns_float_neonemu_fma

#include "tx_float_neonemu.c"
