// Compares the three builds of impl.cpp bit for bit and times them.
//
//   neon-emu-check [quick]
//
// ref  SkNeonEmu.h's lane-wise reference (NEON_EMU_REFERENCE), HSW flags
// fast the shipped HSW build: fast paths and shuffles
// base the shipped baseline x86-64 build: shuffles, no fast paths
//
// Unary float operations run on all 2^32 inputs, vcvt_f32_f16 on all 2^16
// halves, vqrdmulhq_s16 on all 2^32 pairs, srcover8 on every source alpha,
// source and destination byte; the rest on random vectors drawn
// heavily from special values (zeros, subnormals, infinities, NaNs with
// payloads, conversion and overflow boundaries). `quick` samples instead of
// sweeping. Exit status 1 on any difference.
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <vector>

#include "ops.h"

#define DECLARE(name, i0, i1, i2, o, k)                                                  \
  extern "C" void ref_op_##name(unsigned char*, const unsigned char*, const unsigned char*,  \
                             const unsigned char*, unsigned long);                       \
  extern "C" void fast_op_##name(unsigned char*, const unsigned char*, const unsigned char*, \
                              const unsigned char*, unsigned long);                      \
  extern "C" void base_op_##name(unsigned char*, const unsigned char*, const unsigned char*, \
                              const unsigned char*, unsigned long);
NEON_EMU_OPS(DECLARE)

struct Op {
  const char* name;
  int in[3];
  int out;
  char kind;
  neon_emu_op impl[3];
};
#define ENTRY(name, i0, i1, i2, o, k) {#name, {i0, i1, i2}, o, #k[0], {ref_op_##name, fast_op_##name, base_op_##name}},
static const Op kOps[] = {NEON_EMU_OPS(ENTRY)};
static const char* kBuild[3] = {"ref", "fast", "base"};

static const uint32_t kSpecials[] = {
    0x00000000, 0x80000000, 0x00000001, 0x80000001, 0x007fffff, 0x807fffff, 0x00400000,
    0x00200000, 0x001fffff, 0x00800000, 0x80800000, 0x3f800000, 0xbf800000, 0x40000000,
    0x40400000, 0x3f000000, 0xbf000000, 0x3fc00000, 0x3effffff, 0xbf7fffff, 0x7f7fffff,
    0xff7fffff, 0x7f000000, 0x7e800000, 0x7f800000, 0xff800000, 0x7fc00000, 0xffc00000,
    0x7f800001, 0xff800001, 0x7fa00000, 0x7fffffff, 0xffbfffff, 0x4f000000, 0x4effffff,
    0xcf000000, 0xcf000001, 0x4f800000, 0x4f7fffff, 0x477fe000, 0x477ff000, 0x477fefff,
    0x38800000, 0x387fffff, 0x33800000, 0x33000000, 0x33000001, 0x1f800000, 0x5f800000,
    0x3fffffff, 0x40000001,
};
static const int kNumSpecials = sizeof(kSpecials) / sizeof(kSpecials[0]);

static std::mt19937_64 gRng(0x5eed);

static uint32_t lane() {
  uint64_t r = gRng();
  switch (r % 8) {
    case 0:
    case 1:
      return kSpecials[(r >> 8) % kNumSpecials];
    case 2:
      return (uint32_t)(r >> 32);
    default: {
      uint32_t e = 100 + (uint32_t)((r >> 8) % 55);
      return (uint32_t)(r >> 32 & 0x807fffff) | (e << 23);
    }
  }
}

// Float lanes for one input; b (j = 1) sometimes copies a's lane or its
// negation (min/max ties), or sits where a*b nears 2^127 (FRSQRTS's bound).
static void fill_float(unsigned char* in[3], const int bytes[3], size_t n) {
  for (size_t v = 0; v < n; v++) {
    for (int l = 0; l < 4; l++) {
      uint32_t x[3];
      for (int j = 0; j < 3; j++) x[j] = lane();
      uint64_t r = gRng();
      if (r % 8 == 0) x[1] = x[0];
      if (r % 16 == 1) x[1] = x[0] ^ 0x80000000u;
      if (r % 8 == 2) {
        int ea = 1 + (int)((r >> 8) % 254), eb = 379 + (int)((r >> 16) % 5) - 2 - ea;
        eb = eb < 0 ? 0 : eb > 254 ? 254 : eb;
        x[0] = (x[0] & 0x807fffffu) | ((uint32_t)ea << 23);
        x[1] = (x[1] & 0x807fffffu) | ((uint32_t)eb << 23);
      }
      for (int j = 0; j < 3; j++) {
        if (bytes[j]) memcpy(in[j] + v * bytes[j] + l * 4, &x[j], 4);
      }
    }
  }
}

static void fill_bytes(unsigned char* p, size_t len) {
  for (size_t i = 0; i < len; i++) p[i] = (unsigned char)gRng();
}

static int failures = 0;

// Runs every build on n vectors and compares each with ref.
static void compare(const Op& op, unsigned char* in[3], size_t n, std::vector<unsigned char> out[3]) {
  for (int b = 0; b < 3; b++) op.impl[b](out[b].data(), in[0], in[1], in[2], n);
  for (int b = 1; b < 3; b++) {
    if (!memcmp(out[0].data(), out[b].data(), n * op.out)) continue;
    for (size_t v = 0; v < n; v++) {
      if (!memcmp(out[0].data() + v * op.out, out[b].data() + v * op.out, op.out)) continue;
      printf("MISMATCH %s %s, vector:", op.name, kBuild[b]);
      for (int j = 0; j < 3; j++) {
        if (!op.in[j]) continue;
        printf(" in%d=", j);
        for (int i = 0; i < op.in[j]; i++) printf("%02x", in[j][v * op.in[j] + i]);
      }
      printf(" ref=");
      for (int i = 0; i < op.out; i++) printf("%02x", out[0][v * op.out + i]);
      printf(" %s=", kBuild[b]);
      for (int i = 0; i < op.out; i++) printf("%02x", out[b][v * op.out + i]);
      printf("\n");
      failures++;
      return;
    }
  }
}

static const size_t kChunk = 1 << 16;

static void sweep_unary32(const Op& op, bool quick) {
  std::vector<unsigned char> buf(kChunk * 16), out[3];
  for (auto& o : out) o.resize(kChunk * op.out);
  unsigned char* in[3] = {buf.data(), nullptr, nullptr};
  uint64_t step = quick ? 4099 : 1;
  for (uint64_t x = 0; x < (1ull << 32);) {
    size_t n = 0;
    for (; n < kChunk && x < (1ull << 32); n++) {
      for (int l = 0; l < 4; l++, x += step) {
        uint32_t u = (uint32_t)x;
        memcpy(buf.data() + n * 16 + l * 4, &u, 4);
      }
    }
    compare(op, in, n, out);
  }
}

static void sweep_f16(const Op& op) {
  std::vector<unsigned char> buf(16384 * 8), out[3];
  for (auto& o : out) o.resize(16384 * op.out);
  for (uint32_t h = 0; h < 65536; h++) {
    uint16_t v = (uint16_t)h;
    memcpy(buf.data() + h * 2, &v, 2);
  }
  unsigned char* in[3] = {buf.data(), nullptr, nullptr};
  compare(op, in, 16384, out);
}

static void sweep_sqrdmulh(const Op& op, bool quick) {
  const size_t n = 8192;  // every b once per a
  std::vector<unsigned char> a(n * 16), b(n * 16), out[3];
  for (auto& o : out) o.resize(n * 16);
  for (uint32_t i = 0; i < 65536; i++) {
    int16_t v = (int16_t)i;
    memcpy(b.data() + i * 2, &v, 2);
  }
  unsigned char* in[3] = {a.data(), b.data(), nullptr};
  for (uint32_t x = 0; x < 65536; x += quick ? 257 : 1) {
    int16_t v = (int16_t)x;
    for (size_t i = 0; i < n * 8; i++) memcpy(a.data() + i * 2, &v, 2);
    compare(op, in, n, out);
  }
  // the one pair whose product overflows, on its own
  int16_t m = -32768;
  for (size_t i = 0; i < 8; i++) memcpy(a.data() + i * 2, &m, 2), memcpy(b.data() + i * 2, &m, 2);
  compare(op, in, 1, out);
}

// Source-over: every source alpha and source byte against every destination
// byte (the source's colour bytes all s, its alpha sa).
static void sweep_srcover(const Op& op) {
  const size_t n = 8;  // 8 vectors of 8 pixels: 256 destination bytes
  std::vector<unsigned char> src(n * 32), dst(n * 32), out[3];
  for (auto& o : out) o.resize(n * 32);
  for (size_t i = 0; i < n * 32; i++) dst[i] = (unsigned char)i;
  unsigned char* in[3] = {src.data(), dst.data(), nullptr};
  for (int sa = 0; sa < 256; sa++) {
    for (int s = 0; s < 256; s++) {
      for (size_t p = 0; p < n * 8; p++) {
        src[p * 4 + 0] = src[p * 4 + 1] = src[p * 4 + 2] = (unsigned char)s;
        src[p * 4 + 3] = (unsigned char)sa;
      }
      compare(op, in, n, out);
    }
  }
}

static void random_vectors(const Op& op, size_t total) {
  std::vector<unsigned char> buf[3], out[3];
  unsigned char* in[3] = {nullptr, nullptr, nullptr};
  for (int j = 0; j < 3; j++) {
    buf[j].resize(kChunk * (op.in[j] ? op.in[j] : 1));
    in[j] = op.in[j] ? buf[j].data() : nullptr;
  }
  for (auto& o : out) o.resize(kChunk * op.out);
  for (size_t done = 0; done < total; done += kChunk) {
    if (op.kind == 'F') {
      fill_float(in, op.in, kChunk);
    } else {
      for (int j = 0; j < 3; j++) {
        if (op.in[j]) fill_bytes(in[j], kChunk * op.in[j]);
      }
    }
    compare(op, in, kChunk, out);
  }
}

// ns per vector for each build, on ordinary inputs (normal floats).
static void time_op(const Op& op) {
  const size_t n = 1 << 14;
  std::vector<unsigned char> buf[3], out(n * op.out);
  for (int j = 0; j < 3; j++) {
    buf[j].resize(n * (op.in[j] ? op.in[j] : 1));
    for (size_t i = 0; i + 4 <= buf[j].size(); i += 4) {
      uint64_t r = gRng();
      uint32_t u = (op.kind == 'F') ? ((uint32_t)(r & 0x7fffff) | ((uint32_t)(118 + r % 16) << 23) |
                                       (uint32_t)((r >> 40) & 1) << 31)
                                    : (uint32_t)r;
      if (op.kind == 'F' && (!strncmp(op.name, "vrsqrte", 7) || !strncmp(op.name, "vsqrt", 5) ||
                             strstr(op.name, "_u32_"))) {
        u &= 0x7fffffffu;
      }
      memcpy(buf[j].data() + i, &u, 4);
    }
  }
  double ns[3];
  for (int b = 0; b < 3; b++) {
    double best = 1e30;
    for (int rep = 0; rep < 5; rep++) {
      auto t0 = std::chrono::steady_clock::now();
      for (int k = 0; k < 20; k++) op.impl[b](out.data(), buf[0].data(), buf[1].data(), buf[2].data(), n);
      double t = std::chrono::duration<double, std::nano>(std::chrono::steady_clock::now() - t0).count() /
                 (20.0 * n);
      best = t < best ? t : best;
    }
    ns[b] = best;
  }
  printf("  %-16s ref %7.2f  fast %7.2f  base %7.2f ns/vector   ref/fast %5.1fx\n", op.name, ns[0], ns[1],
         ns[2], ns[0] / ns[1]);
}

int main(int argc, char** argv) {
  bool quick = argc > 1 && !strcmp(argv[1], "quick");
  for (const Op& op : kOps) {
    auto t0 = std::chrono::steady_clock::now();
    if (!strcmp(op.name, "vcvt_f32_f16")) {
      sweep_f16(op);
      random_vectors(op, 1 << 18);
    } else if (!strcmp(op.name, "srcover8")) {
      sweep_srcover(op);
      random_vectors(op, 1 << 18);
    } else if (!strcmp(op.name, "vqrdmulhq_s16")) {
      sweep_sqrdmulh(op, quick);
    } else if (op.kind == 'F' && !op.in[1]) {
      sweep_unary32(op, quick);
    } else {
      random_vectors(op, quick ? (1 << 18) : (op.kind == 'M' ? (1 << 20) : (1 << 24)));
    }
    printf("%-16s checked in %.1f s\n", op.name,
           std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count());
    fflush(stdout);
  }
  printf("timing:\n");
  for (const Op& op : kOps) time_op(op);
  printf(failures ? "FAILED: %d operations differ\n" : "all builds agree\n", failures);
  return failures ? 1 : 0;
}
