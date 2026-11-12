// MouseDispatch._crossing: where and when a humanized curve leaves the page.
// Stock 159.0.1 on X11 (context/measure-kit/exit-from-rest, and the guard
// humanize-mouse-trajectory.py) puts the mouseout one 1 kHz sample after the
// last mousemove: 1px or more past the edge, and one sample's travel from it,
// at most 14.9px at the fastest flick measured (15 px/ms).
import assert from 'node:assert/strict';
import {test} from 'node:test';
import './gecko.mjs';

// MouseDispatch imports Helper.js and Timer.sys.mjs at load; _crossing needs
// neither, so stand-ins are enough.
const importESModule = globalThis.ChromeUtils.importESModule;
globalThis.ChromeUtils.importESModule = url => {
  if (url === 'resource://gre/modules/juggler/Helper.js')
    return {Helper: class {}};
  if (url === 'resource://gre/modules/Timer.sys.mjs')
    return {setTimeout, clearTimeout};
  return importESModule(url);
};
const {MouseDispatch} = await import('../../additions/juggler/input/MouseDispatch.js');

const BOX = {left: 0, top: 85, width: 1280, height: 800};
const STOCK_MAX_SAMPLE_PX = 15;

function crossing(from, to) {
  const dispatch = new MouseDispatch(null, BOX);
  return dispatch._crossing(from, to);
}

function apart(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

test('an exit is one stock sample past the last point the page saw', () => {
  for (const [from, to] of [
    [{x: 40, y: 2, t: 0}, {x: 56.4, y: -1.6, t: 8}],
    [{x: 400, y: 1, t: 0}, {x: 401, y: -3, t: 16}],
    [{x: 3, y: 300, t: 0}, {x: -9, y: 305, t: 8}],
  ]) {
    const {last, exit} = crossing(from, to);
    const seen = last ?? {x: Math.round(from.x), y: Math.round(from.y)};
    assert.ok(exit.x < 0 || exit.y < 0, JSON.stringify({from, to, exit}));
    assert.ok(apart(seen, exit) >= 2, JSON.stringify({seen, exit}));
    assert.ok(apart(seen, exit) <= STOCK_MAX_SAMPLE_PX, JSON.stringify({seen, exit}));
  }
});

test('a step whose planned time rounded to nothing still leaves at a stock speed', () => {
  // toSteps rounds each recorded time to a whole ms, so a step can carry 16px
  // in 0 ms. Taken at face value the exit lands on the whole step, 16.3px
  // from the last move the page saw, which no 1 kHz mouse reports (CI,
  // camoufox-free#37: (40, 2) -> (56, -1)).
  for (const dt of [0, 1]) {
    const from = {x: 40, y: 2, t: 100};
    const to = {x: 56.4, y: -1.6, t: 100 + dt};
    const {last, exit} = crossing(from, to);
    const seen = last ?? {x: 40, y: 2};
    assert.ok(exit.y < 0, JSON.stringify({dt, exit}));
    assert.ok(apart(seen, exit) <= STOCK_MAX_SAMPLE_PX, JSON.stringify({dt, seen, exit}));
  }
});
