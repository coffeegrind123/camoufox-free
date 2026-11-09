/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

"use strict";

/**
 * The cursor path `humanize=True` moves along.
 *
 * Camoufox used to generate this in C++ (additions/camoucfg/MouseTrajectories.hpp):
 * a cubic Bezier through two random knots, distorted, then walked with an
 * ease-out and emitted at a flat 10ms cadence. It was replaced by Cursory
 * (cursory/, vendored) because the two differ in what they are imitating. A
 * Bezier is an equation, and an equation sampled at a fixed rate has velocity
 * and jerk profiles that separate cleanly from a hand's; the old path's speed
 * also came entirely from an easing function, so every movement Camoufox ever
 * made accelerated and decelerated the same way. Cursory replays one of 2356
 * movements recorded from real people, morphed onto the requested endpoints,
 * and keeps that recording's own timing -- pauses, overshoots and all.
 *
 * `humanize:engine` = "mousecrack" swaps in a second generator for moves
 * (mousecrack/, vendored): a recurrent network trained on recorded movements
 * that synthesizes a new path rather than replaying one. Measured against the
 * same recordings, its medium and long moves are slower and wander more than a
 * hand's or Cursory's, so Cursory stays the default.
 *
 * This module is the whole boundary between Camoufox and both generators: it
 * owns the cadence and the pixel grid. Wheel notches are planned here too.
 */

const kCursoryUrl = 'resource://gre/modules/juggler/input/cursory/cursory.js';
const kMousecrackUrl = 'resource://gre/modules/juggler/input/mousecrack/mousecrack.js';

// A mousecrack path that never gets within 3px of the target would end in a
// jump onto it. Measured: 2 of 300 moves; a fresh draw almost always arrives.
const kMousecrackAttempts = 3;

// A page's first move comes down from the toolbar onto the page. A draw that
// climbs back out of the page first is redrawn this many times: no hand heading
// for a point below climbs 270px back into the toolbar on the way (measured:
// 15 of 40 mousecrack entry draws left the page, by up to 274px).
const kEntryAttempts = 3;

/** Does every point ([x, y] or {x, y}) stay inside `within` ({width, height})? */
function staysWithin(points, within) {
  return points.every(point => {
    const px = Math.round(Array.isArray(point) ? point[0] : point.x);
    const py = Math.round(Array.isArray(point) ? point[1] : point.y);
    return px >= 0 && py >= 0 && px < within.width && py < within.height;
  });
}

/**
 * Samples per second.
 *
 * A USB mouse reports at 125Hz, but Gecko coalesces moves to the refresh rate
 * before a page sees them, so 60 is what a page observes from a real cursor on
 * a 60Hz display -- and it is the rate the recordings themselves carry (median
 * gap across all 110664 of their samples: 16ms). Asking for more would not add
 * information, only more synthesized events per move, each of which costs a
 * round trip to the renderer and an ack.
 */
const kFrequencyHz = 60;

/**
 * Default ceiling on how long one movement may take, in seconds.
 *
 * Matches what Camoufox has always documented ("the cursor typically takes up
 * to 1.5 seconds to move across the window") and what the old generator's
 * default worked out to: 150 points at 10ms each. Cursory's own durations come
 * from the recordings and normally land well inside this, so the cap is a
 * backstop against a slow recording, not the thing setting the pace.
 */
const kDefaultMaxTimeSeconds = 1.5;

// Loaded on first use, not at import: the recording database is ~2MB of JSON,
// and a profile that never sets humanize=True should never pay for it.
//
// Measured: ~33ms to read, parse and index, once per process. Generating one
// path afterwards is ~0.5ms (p95 under 1ms, and flat in distance), against a
// movement that then takes several hundred milliseconds to play out -- so the
// generator is nowhere near the cost of the move it describes.
let cursoryModule = null;

function loadCursory() {
  if (!cursoryModule)
    cursoryModule = ChromeUtils.importESModule(kCursoryUrl);
  return cursoryModule;
}

let mousecrackModule = null;

function loadMousecrack() {
  if (!mousecrackModule)
    mousecrackModule = ChromeUtils.importESModule(kMousecrackUrl);
  return mousecrackModule;
}

/** The configured move engine: "mousecrack", or Cursory for anything else. */
function moveEngine() {
  let name = '';
  try {
    name = ChromeUtils.camouGetString('humanize:engine') || '';
  } catch (e) {}
  return name === 'mousecrack' ? 'mousecrack' : 'cursory';
}

/** The configured [min, max] duration of one movement, in milliseconds. */
function durationBoundsMs({maxTime = kDefaultMaxTimeSeconds, minTime = 0}) {
  const maxMs = Math.max(0, maxTime * 1000);
  // A min above the max would make the clamp below non-monotonic; the max wins,
  // as it did in C++ (std::min of the two point counts).
  return {minMs: Math.min(Math.max(0, minTime * 1000), maxMs), maxMs};
}

/**
 * The scale that puts a path of `naturalMs` inside the configured bounds.
 *
 * Scale the whole path's timing into the bounds rather than truncating it.
 * Truncating would drop the end of every long movement, which is the part that
 * decelerates onto the target -- the most recognizably human part of it.
 */
function durationScale(naturalMs, options) {
  const {minMs, maxMs} = durationBoundsMs(options);
  return naturalMs > 0 ? Math.min(Math.max(naturalMs, minMs), maxMs) / naturalMs : 0;
}

/**
 * A path's points as a plan's steps, ending on `to`.
 *
 * `times[i]` is point i's time in ms from the start of the move, already
 * scaled; `totalMs` is when the destination is due.
 *
 * A real mouse reports whole pixels, and the widget rounds to a device pixel
 * before hit-testing anyway, so round here and drop points that land on the
 * pixel the cursor is already on. Those are not merely redundant: a
 * zero-displacement move generates no eMouseMove, so it is never acked, and
 * waiting for that ack is one of the deadlocks docs/input-dispatch.md exists
 * to prevent. Their elapsed time is kept -- a hand that hovers a pixel for
 * 30ms took 30ms -- and folded into the next point that does move.
 *
 * This is also why the event rate is only ever *at most* kFrequencyHz: a
 * short move has fewer whole pixels along it than samples, so it reports
 * fewer events, exactly as a real mouse crossing the same distance would.
 * Measured with a 3s floor: 41Hz over 72px, 56Hz over 400px, 60Hz over
 * 2100px.
 */
function toSteps(from, to, points, times, totalMs) {
  const steps = [];
  let previousX = Math.round(from.x);
  let previousY = Math.round(from.y);
  const destinationX = Math.round(to.x);
  const destinationY = Math.round(to.y);
  let t = 0;

  // The first point is where the cursor already is, and the last is the
  // destination, appended below; both ends are excluded.
  for (let i = 1; i < points.length - 1; i++) {
    const x = Math.round(points[i][0]);
    const y = Math.round(points[i][1]);
    if (x === previousX && y === previousY)
      continue;
    // Landing on the destination early would leave the final step with
    // nothing to move, and the same unacked wait.
    if (x === destinationX && y === destinationY)
      continue;
    t = Math.max(t, Math.round(times[i]));
    steps.push({kind: 'move', x, y, t});
    previousX = x;
    previousY = y;
  }

  steps.push({kind: 'move', x: to.x, y: to.y, t: Math.max(t, Math.round(totalMs))});
  return steps;
}

/**
 * Past this multiple of its budget, a move whose acks are stalling
 * fast-forwards to its destination. It holds the process-wide activation slot
 * while it plays (kActivationSlotBudgetMs, 30s).
 */
const kDeadlineFactor = 1.5;

const kPxPerNotch = 100;
const kLinesPerNotch = 3;
const kPxPerMacLine = 16;
const kMaxMacLines = 12;

function toNotches(delta) {
  const count = delta === 0 ? 0 : Math.max(1, Math.round(Math.abs(delta) / kPxPerNotch));
  return new Array(count).fill(Math.sign(delta) * kLinesPerNotch);
}

// macOS accelerates a turn: every recorded burst starts at one line and grows
// (docs/input-dispatch.md).
function toMacLines(delta, rng) {
  let left = delta === 0 ? 0 : Math.max(1, Math.round(Math.abs(delta) / kPxPerMacLine));
  const events = [];
  for (let size = 1; left > 0; size = Math.min(kMaxMacLines, size + 1 + Math.floor(rng() * 3))) {
    const lines = Math.min(size, left);
    events.push(Math.sign(delta) * lines);
    left -= lines;
  }
  return events;
}

/**
 * Plans a humanized mousemove from `ctx.cursor` to `to`.
 *
 * Coordinates are browser-relative, exactly as MouseDispatch wants them. The
 * plan's steps are `{kind: 'move', x, y, t}` with `t` in ms from the start of
 * the move, and the last step is always the destination itself: the move has
 * to finish exactly on the requested coordinate whatever happens to the curve,
 * and it is the one point that must not be dropped for being off-screen or
 * off-grid. Every other step is garnish that dispatch may drop.
 *
 * `ctx.options` carries `humanize:maxTime` / `humanize:minTime` (seconds), and
 * `ctx.rng` is the only randomness used.
 */
export const cursory = {
  budgetMs(options) {
    return durationBoundsMs(options).maxMs;
  },

  planMove(ctx, to) {
    const destination = {kind: 'move', x: to.x, y: to.y};
    const {x: fromX, y: fromY} = ctx.cursor;
    // parkOffContent() forgets the cursor position (it sets NaN) because the
    // pointer really did move somewhere untracked. With no start point there is
    // no path to draw, so this move goes straight to its destination.
    if (!Number.isFinite(fromX) || !Number.isFinite(fromY))
      return {steps: [{...destination, t: 0}], endState: {cursor: to}};

    const {generateTrajectory} = loadCursory();

    // Cursory takes a 48-bit seed, reused below.
    const seed = Math.floor(ctx.rng() * 2 ** 32) * 2 ** 16 + Math.floor(ctx.rng() * 2 ** 16);
    let {points, timings} = generateTrajectory(
        [fromX, fromY], [to.x, to.y], {frequency: kFrequencyHz, seed});

    const recordedMs = timings[timings.length - 1];
    const scale = durationScale(recordedMs, ctx.options);

    // Rescaling the clock without rescaling the sample count would change the
    // rate the events come out at, and the rate is itself a fingerprint. Measured
    // over 1500 moves: 1.8% run past the 1.5s default cap, and the worst was a 5s
    // recording -- 301 points, which compressed into 1.5s is a 200Hz burst, above
    // what any mouse reports and far above what any display coalesces to. A
    // minTime floor has the same problem pointing the other way, stretching a
    // move until it ticks at 14Hz.
    //
    // So ask for the sample count that lands at kFrequencyHz once scaled. The
    // seed is reused deliberately: the recording is chosen before `frequency` is
    // consulted, so the same seed re-picks the same recording with the same
    // natural duration, and `scale` stays exact. Only the resampling differs.
    if (scale > 0 && scale !== 1) {
      ({points, timings} = generateTrajectory(
          [fromX, fromY], [to.x, to.y],
          {frequency: Math.max(1, kFrequencyHz * scale), seed}));
    }

    const steps = toSteps({x: fromX, y: fromY}, to, points,
        timings.map(t => t * scale), recordedMs * scale);
    return {steps, endState: {cursor: to}};
  },

  planWheel(ctx, at, {deltaX, deltaY, deltaZ}) {
    const eventsFor = delta => (ctx.macOS ? toMacLines(delta, ctx.rng) : toNotches(delta));
    const xs = eventsFor(deltaX);
    const ys = eventsFor(deltaY);
    const count = Math.max(1, xs.length, ys.length);
    const steps = [];
    let t = 0;
    for (let i = 0; i < count; i++) {
      if (i)
        t += 18 + ctx.rng() * 42;
      const dx = xs[i] ?? 0;
      const dy = ys[i] ?? 0;
      steps.push({
        kind: 'wheel', t, x: at.x, y: at.y,
        dx, dy, dz: i ? 0 : deltaZ,
        mode: 1,
        ticks: {x: dx, y: dy},
        essential: true,
      });
    }
    return {steps, endState: {}};
  },
};

/**
 * Plans a humanized mousemove with mousecrack, in cursory.planMove's shape.
 * Resolves to null when no draw reached the target: a path that never gets
 * within 3px of it would end in a jump onto it, which no hand makes, so the
 * caller draws that move with Cursory instead.
 *
 * mousecrack steps at its own irregular cadence, ~10ms apart. The path is
 * thinned rather than resampled: a point is kept once at least a kFrequencyHz
 * interval of scaled time has passed since the last one kept. Resampling onto
 * an even clock would make every gap identical, a metronome that the model's
 * own uneven timing does not have; thinning keeps each gap a sum of real
 * steps. A path stretched by a minTime floor is not filled in, so it ticks
 * slower.
 *
 * `within` ({width, height}), given for a page's first move, asks for a draw
 * that stays inside the viewport (kEntryAttempts). mousecrack draws with
 * Math.random, not `ctx.rng`.
 *
 * Async because mousecrack computes its path in slices on this thread.
 */
export const mousecrack = {
  budgetMs(options) {
    return durationBoundsMs(options).maxMs;
  },

  async planMove(ctx, to, {within = null} = {}) {
    const {x: fromX, y: fromY} = ctx.cursor;
    if (!Number.isFinite(fromX) || !Number.isFinite(fromY))
      return {steps: [{kind: 'move', x: to.x, y: to.y, t: 0}], endState: {cursor: to}};

    const {generateTrajectory} = loadMousecrack();
    const accepted = path => path.converged && (!within || staysWithin(path.points, within));
    const attempts = within ? Math.max(kMousecrackAttempts, kEntryAttempts) : kMousecrackAttempts;
    let path = null;
    for (let attempt = 0; attempt < attempts && !(path && accepted(path)); attempt++)
      path = await generateTrajectory([fromX, fromY], [to.x, to.y]);
    if (!path || !accepted(path))
      return null;

    const {points, timings} = path;
    const naturalMs = timings[timings.length - 1];
    const scale = durationScale(naturalMs, ctx.options);
    const totalMs = naturalMs * scale;
    const minGapMs = 1000 / kFrequencyHz;
    const kept = [points[0]];
    const keptTimes = [0];
    for (let i = 1; i < points.length - 1; i++) {
      const t = timings[i] * scale;
      if (t - keptTimes[keptTimes.length - 1] >= minGapMs) {
        kept.push(points[i]);
        keptTimes.push(t);
      }
    }
    kept.push(points[points.length - 1]);
    keptTimes.push(totalMs);
    return {steps: toSteps(ctx.cursor, to, kept, keptTimes, totalMs), endState: {cursor: to}};
  },
};

/**
 * The plan for a `humanize=True` move, and when pacing it must give up.
 *
 * `within` ({width, height}), given for a page's first move, asks for a path
 * that stays inside the viewport: a cursor coming down from the toolbar does
 * not climb back out of the page on its way to a point below. A Cursory draw
 * that leaves it is redrawn up to kEntryAttempts times; if every draw leaves,
 * the last one plays and MouseDispatch takes the pointer off the page and back,
 * as a real one would.
 */
export async function humanizedMove(cursor, to, {within = null} = {}) {
  const options = {
    maxTime: ChromeUtils.camouGetDouble('humanize:maxTime', kDefaultMaxTimeSeconds),
    minTime: ChromeUtils.camouGetDouble('humanize:minTime', 0),
  };
  const ctx = {cursor, options, rng: Math.random};
  let plan = moveEngine() === 'mousecrack' ? await mousecrack.planMove(ctx, to, {within}) : null;
  if (!plan) {
    plan = cursory.planMove(ctx, to);
    for (let attempt = 1; within && attempt < kEntryAttempts && !staysWithin(plan.steps, within); attempt++)
      plan = cursory.planMove(ctx, to);
  }
  return {
    plan,
    deadlineMs: cursory.budgetMs(options) * kDeadlineFactor,
  };
}
