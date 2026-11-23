/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// SkOpts_armhsw.cpp built with AVX-512 F, DQ, BW and VL (gfx/skia/moz.build):
// the same AVX2-width stages, now with 32 vector registers and EVEX forms, for
// general.cpu_identity = ARM64 on a CPU that has them. The exact AArch64
// helpers keep more values live than AVX2's 16 registers hold, and the spills
// were about a tenth of the hue stage. Same source, same IEEE operations,
// same bits; without AVX512CD Skia's own tier selection stays at AVX2.

#include "src/core/SkOpts.h"

#if defined(SK_CPU_X86) && !defined(SK_ENABLE_OPTIMIZE_SIZE)

#define SK_OPTS_NS armskx
#define SKRP_ARM_SEMANTICS 1
#include "src/opts/SkRasterPipeline_opts.h"

namespace SkOpts {
    void Init_armskx() {
        raster_pipeline_lowp_stride  = SK_OPTS_NS::raster_pipeline_lowp_stride();
        raster_pipeline_highp_stride = SK_OPTS_NS::raster_pipeline_highp_stride();

    #define M(st) ops_highp[(int)SkRasterPipelineOp::st] = (StageFn)SK_OPTS_NS::st;
        SK_RASTER_PIPELINE_OPS_ALL(M)
        just_return_highp = (StageFn)SK_OPTS_NS::just_return;
        start_pipeline_highp = SK_OPTS_NS::start_pipeline;
    #undef M

    #define M(st) ops_lowp[(int)SkRasterPipelineOp::st] = (StageFn)SK_OPTS_NS::lowp::st;
        SK_RASTER_PIPELINE_OPS_LOWP(M)
        just_return_lowp = (StageFn)SK_OPTS_NS::lowp::just_return;
        start_pipeline_lowp = SK_OPTS_NS::lowp::start_pipeline;
    #undef M
    }
}  // namespace SkOpts

#endif  // SK_CPU_X86 && !SK_ENABLE_OPTIMIZE_SIZE
