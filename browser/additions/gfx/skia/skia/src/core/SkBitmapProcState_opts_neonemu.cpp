/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// Skia's AArch64 bilinear samplers on x86-64, for general.cpu_identity = ARM64.

#include "include/private/base/SkFeatures.h"

#if defined(SK_CPU_X86) && !defined(SK_ENABLE_OPTIMIZE_SIZE)

#include "include/core/SkTypes.h"
#include "include/private/base/SkFeatures.h"
#include "include/private/base/SkMalloc.h"
#include "include/private/base/SkSpan_impl.h"
#include "include/private/base/SkTemplates.h"
#include "modules/skcms/skcms.h"
#include "src/base/SkMSAN.h"
#include "src/base/SkUtils.h"
#include "src/base/SkVx.h"
#include "src/core/Sk4px.h"
#include "src/core/SkBitmapProcState.h"
#include "src/core/SkBlitMask.h"
#include "src/core/SkBlitRow.h"
#include "src/core/SkColorData.h"
#include "src/core/SkOpts.h"
#include "src/core/SkRasterPipeline.h"
#include "src/core/SkRasterPipelineContextUtils.h"
#include "src/core/SkSwizzlePriv.h"
#include "src/shaders/SkPerlinNoiseShaderType.h"
#include "src/sksl/tracing/SkSLTraceHook.h"

#include "src/opts/SkOpts_NeonEmuTarget.h"

#include "src/opts/SkBitmapProcState_opts.h"
#include "src/opts/SkNeonEmuAffine.h"

#include <cstdlib>

#if defined(SK_NEON_EMU_HSW) && defined(__AVX2__)
static void S32_alpha_D32_filter_DXDY_avx2(const SkBitmapProcState& s,
                                           const uint32_t* xy, int count, SkPMColor* colors) {
    sk_neon_emu_filter_dxdy((const char*)s.fPixmap.addr(), s.fPixmap.rowBytes(), xy, count, colors,
                            s.fAlphaScale);
}
#endif

namespace SkOpts {
    void SK_NEON_EMU_NAME(Init_BitmapProcState_neonemu)() {
        S32_alpha_D32_filter_DX   = SK_OPTS_NS::S32_alpha_D32_filter_DX;
        S32_alpha_D32_filter_DXDY = SK_OPTS_NS::S32_alpha_D32_filter_DXDY;
#if defined(SK_NEON_EMU_HSW) && defined(__AVX2__)
        // Rotated and skewed draws, 4 pixels at a time (SkNeonEmuAffine.h).
        // MOZ_CAMOUFOX_ARM_RASTER_NARROW keeps the emulated ones, as it keeps
        // the 4-wide pipeline, for cpu-arm-raster-wide to compare.
        if (!getenv("MOZ_CAMOUFOX_ARM_RASTER_NARROW")) {
            filter_affine_clamp = sk_neon_emu_filter_affine_clamp;
            S32_alpha_D32_filter_DXDY = S32_alpha_D32_filter_DXDY_avx2;
        }
#endif
    }
}  // namespace SkOpts

#endif  // SK_CPU_X86 && !SK_ENABLE_OPTIMIZE_SIZE
