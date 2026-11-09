// The mousecrack move engine: the same plan contract as Cursory's, and a
// humanized first move that stays on the page.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {load} from './gecko.mjs';

await load('input/mousecrack/mousecrack.js');
const {mousecrack, humanizedMove} = await load('input/CursorTrajectory.js');

const kMinGapMs = 1000 / 60;

function assertPlan(steps, to, budgetMs) {
  const last = steps.at(-1);
  assert.deepEqual([last.x, last.y], [to.x, to.y]);
  assert.ok(last.t <= budgetMs, `${last.t} > ${budgetMs}`);
  for (let j = 1; j < steps.length; j++) {
    assert.ok(steps[j].t >= steps[j - 1].t, 'steps in time order');
    assert.equal(steps[j].kind, 'move');
  }
  for (let j = 1; j < steps.length - 1; j++) {
    assert.ok(Number.isInteger(steps[j].x) && Number.isInteger(steps[j].y), 'whole pixels');
    assert.ok(steps[j].x !== steps[j - 1].x || steps[j].y !== steps[j - 1].y, 'no zero-displacement step');
  }
}

test('plans end exactly on the target, in time order, inside maxTime, or are null', async () => {
  let planned = 0;
  for (const maxTime of [0.3, 1.5]) {
    const options = {maxTime};
    const budgetMs = mousecrack.budgetMs(options);
    assert.equal(budgetMs, maxTime * 1000);
    for (let i = 0; i < 12; i++) {
      const to = {x: (i * 211) % 1280, y: (i * 97) % 720};
      const cursor = {x: (i * 53) % 1280 + 7, y: (i * 31) % 720 + 3};
      const plan = await mousecrack.planMove({cursor, options, rng: Math.random}, to);
      if (!plan)
        continue;
      planned++;
      assertPlan(plan.steps, to, budgetMs);
      assert.deepEqual(plan.endState, {cursor: to});
    }
  }
  // A null plan is a draw that never arrived (2 of 300 measured); most arrive.
  assert.ok(planned >= 20, `only ${planned} of 24 moves planned`);
});

test('thinned intermediate steps keep at least a 60 Hz gap', async () => {
  const options = {maxTime: 1.5};
  for (let i = 0; i < 6; i++) {
    const plan = await mousecrack.planMove({cursor: {x: 10 + i, y: 20}, options, rng: Math.random}, {x: 900, y: 600 - i * 40});
    if (!plan)
      continue;
    const inner = plan.steps.slice(0, -1);
    for (let j = 1; j < inner.length; j++)
      assert.ok(inner[j].t - inner[j - 1].t >= Math.floor(kMinGapMs) - 1, `gap ${inner[j].t - inner[j - 1].t}`);
  }
});

test('an untracked cursor moves straight to the target', async () => {
  const plan = await mousecrack.planMove({cursor: {x: NaN, y: NaN}, options: {}, rng: Math.random}, {x: 10, y: 20});
  assert.deepEqual(plan.steps, [{kind: 'move', x: 10, y: 20, t: 0}]);
});

for (const engine of ['cursory', 'mousecrack']) {
  test(`humanizedMove (${engine}) plans a move and a deadline, mostly on the page for a first move`, async () => {
    globalThis.ChromeUtils.camouGetDouble = (name, fallback) => fallback;
    globalThis.ChromeUtils.camouGetString = name => (name === 'humanize:engine' ? engine : '');
    const within = {width: 1280, height: 720};
    let inside = 0;
    const runs = 10;
    for (let i = 0; i < runs; i++) {
      const to = {x: 100 + i * 100, y: 400 + i * 20};
      const {plan, deadlineMs} = await humanizedMove({x: to.x + 30, y: 1}, to, {within});
      assert.equal(deadlineMs, 1500 * 1.5);
      assertPlan(plan.steps, to, 1500);
      if (plan.steps.every(({x, y}) => x >= 0 && y >= 0 && x < within.width && y < within.height))
        inside++;
    }
    assert.ok(inside >= runs - 2, `${inside} of ${runs} first moves stayed on the page`);
  });
}
