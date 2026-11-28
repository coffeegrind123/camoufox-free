/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// SkBlitMask_opts_neonemu.cpp built for AVX2, FMA and F16C (gfx/skia/moz.build), where
// SkNeonEmu.h runs its fast paths. Chosen over the baseline build on a CPU
// with SkCpu's ML3 features; both compute the same bits.

#define SK_NEON_EMU_HSW 1
#include "src/core/SkBlitMask_opts_neonemu.cpp"
