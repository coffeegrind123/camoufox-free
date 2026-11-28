/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// Skia's raster pipeline computing what its AArch64 tier computes, at AVX2's
// width, for general.cpu_identity = ARM64 on a CPU with AVX2, FMA and F16C
// (SKRP_ARM_SEMANTICS in SkRasterPipeline_opts.h). The 4-wide emulated tier
// (SkOpts_neonemu*.cpp) gives the same bits about twice as slowly per pixel,
// which a page can time; it stays for older CPUs and as the reference.

#include "src/core/SkOpts.h"

#if defined(SK_CPU_X86) && !defined(SK_ENABLE_OPTIMIZE_SIZE)

#define SK_OPTS_NS armhsw
#define SKRP_ARM_SEMANTICS 1
#include "src/opts/SkRasterPipeline_opts.h"

namespace SkOpts {
    void Init_armhsw() {
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
