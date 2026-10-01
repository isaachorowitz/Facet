import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import ts from 'typescript';

// Compile the pure TypeScript modules in memory, using the existing compiler dependency.
const modules = new Map();
async function load(relative) {
  const url = new URL(relative, import.meta.url);
  if (modules.has(url.href)) return modules.get(url.href);
  const source = await readFile(url, 'utf8');
  let compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
  const imports = [...compiled.matchAll(/from ['"]([^'"]+)['"]/g)];
  for (const match of imports) {
    const child = new URL(`${match[1]}.ts`, url);
    const childData = await load(new URL(child).href);
    compiled = compiled.replace(match[0], `from '${childData}'`);
  }
  const data = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`;
  modules.set(url.href, data);
  return data;
}
const presentation = await import(await load('../src/lib/presentation.ts'));
const figure = await import(await load('../src/lib/figure.ts'));
const chart = await import(await load('../src/lib/chart.ts'));
const validation = await import(await load('../src/api/validate.ts'));

test('mood spelling and sentence thresholds preserve the page', () => {
  assert.equal(presentation.capitalise('focused'), 'Focused');
  assert.equal(presentation.capitalise('head_on_hand'), 'Head_on_hand');
  assert.equal(presentation.sentence({ frowning: .7, jaw_clenched: .7, eyes_heavy: .2,
    smiling: .1, activity: { choice: 'working' }, stress: 2.5, fatigue: 2 }),
    "Brow furrowed, lips pressed. Looks like you're working. Stress is high. Looking tired.");
});
test('chart lines break for missing values and gaps over twenty minutes', () => {
  assert.equal(presentation.linePath([{ t: 0, stress: 0 }, { t: 1 }, { t: 2, stress: 4 }, { t: 1303, stress: 2 }], 'stress', t => t),
    'M0.0,117.0M2.0,3.0M1303.0,60.0');
});
test('posture coordinates mirror around the shoulder centre', () => {
  const points = figure.figurePoints({ visible: true, skeleton: { l_sh: [.4, .5, 1], r_sh: [.8, .5, 1], nose: [.7, .2, 1] } });
  assert.ok(Math.abs(points.l_sh[0] - 48) < .0001);
  assert.ok(Math.abs(points.r_sh[0] + 48) < .0001);
  assert.ok(points.nose[0] < 0);
  assert.equal(figure.figurePoints({ visible: true, skeleton: {} }), null);
});
test('live window expires old points and tooltip rejects distant points', () => {
  const model = chart.chartModel('live', null, [{ t: 399, expression: 'sad' }, { t: 990, expression: 'happy', stress: 1 }], 1000);
  assert.equal(model.points.length, 1);
  assert.equal(model.t0, 400);
  assert.equal(model.t1, 1000);
  assert.equal(model.strip.length, 64);
  assert.equal(chart.nearestPoint(model.points, 920, 60), null);
  assert.equal(chart.nearestPoint(model.points, 950, 60)?.t, 990);
});
test('day chart expands around readings and respects day boundaries', () => {
  const model = chart.chartModel('day', { start: 0, bucket_minutes: 5, points: [{ t: 1800 }, { t: 85000 }] }, [], 1000);
  assert.equal(model.t0, 0);
  assert.equal(model.t1, 86400);
});
test('network validation rejects malformed JSON and accepts empty history', () => {
  assert.throws(() => validation.parseMessage({ type: 'live', face: {} }));
  assert.throws(() => validation.parseTimeline({ start: '0', bucket_minutes: 5, points: [] }));
  assert.deepEqual(validation.parseTimeline({ start: 0, bucket_minutes: 5, points: [] }).points, []);
  assert.deepEqual(validation.parseSpeech([]), []);
});
if (process.env.FACET_CONTRACT_SMOKE === '1') {
  test('read-only backend payloads conform to the contract', async () => {
    for (const [path, parse] of [['state', validation.parseState], ['timeline', validation.parseTimeline], ['summary', validation.parseSummary], ['speech?minutes=240', validation.parseSpeech]]) {
      const response = await fetch(`http://127.0.0.1:8765/api/${path}`, { method: 'GET', signal: AbortSignal.timeout(15000) });
      assert.equal(response.ok, true, path);
      parse(await response.json());
    }
  });
}

const v2 = await import(await load('../src/lib/v2.ts'));
const fixture = JSON.parse(await readFile(new URL('./v2.fixture.json', import.meta.url), 'utf8'));
test('v2 and v1 live shapes validate, while malformed new fields are rejected', () => {
  assert.equal(validation.parseMessage(fixture.live).hands.length, 2);
  const { view, hands, wellness, caption, focus_session, ...v1 } = fixture.live;
  delete v1.posture.stale;
  assert.equal(validation.parseMessage(v1).hands, undefined);
  assert.throws(() => validation.parseMessage({ ...fixture.live, hands: [{ ...hands[0], landmarks: [[0, 0]] }] }));
  assert.throws(() => validation.parseMessage({ ...fixture.live, view: { ...view, w: 0 } }));
  assert.equal(validation.parseSummary(fixture.summary).sips, 7);
  assert.deepEqual(validation.parseRecap({ date: '2026-10-01', text: null }), { date: '2026-10-01', text: null });
  assert.throws(() => validation.parseRecap({ text: 3 }));
  assert.equal(validation.parseFocusSession(null), null);
  assert.equal(validation.parseCaptions([caption]).length, 1);
  assert.equal(validation.parseMarks(fixture.marks).length, 3);
});
test('all v2 socket events and notification kinds are accepted', () => {
  for (const type of ['gesture', 'mark', 'caption', 'focus', 'face_touch']) {
    const data = { gesture: { ts: 1, gesture: 'ILoveYou', hand: 'Left', action: null }, mark: fixture.marks[0],
      caption: fixture.caption, focus: { state: 'ended', session: { started: 1, ends: 1501, minutes: 25 } }, face_touch: { ts: 1, count_last_hour: 3 } }[type];
    assert.equal(validation.parseMessage({ type, data }).type, type);
  }
  for (const kind of ['eyes', 'blink', 'hydrate', 'stand']) assert.equal(validation.parseMessage({type:'notification',data:{kind,text:'A gentle nudge'}}).data.kind, kind);
});
test('hands map through the crop, object-fit cover, then horizontal reflection', () => {
  const view = { x: .2, y: .1, w: .5, h: .6 };
  const close = (a,b) => assert.ok(Math.abs(a - b) < .00001, `${a} != ${b}`);
  const centre = v2.mirrorPoint([.45,.4],view,360,300);
  close(centre[0],180); close(centre[1],150);
  const corner = v2.mirrorPoint([.2,.1],view,360,300);
  close(corner[0],360); close(corner[1],0);
  const tall = v2.mirrorPoint([.2,.1],view,300,600);
  close(tall[0],510); close(tall[1],0); // Outside the SVG is clipped, exactly like the video.
  const wide = v2.mirrorPoint([.45,.1],view,720,300);
  close(wide[0],360); close(wide[1],-150);
});
test('captions expire precisely at 40 seconds and focus countdown never goes negative', () => {
  assert.equal(v2.freshCaption({ts:100,text:'A quiet rhythm'},139.99),true);
  assert.equal(v2.freshCaption({ts:100,text:'A quiet rhythm'},140),false);
  assert.equal(v2.freshCaption({ts:141,text:'Future caption'},140),false);
  assert.equal(v2.freshCaption({ts:100,text:'  '},110),false);
  assert.equal(v2.freshCaption(null,100),false);
  assert.equal(v2.focusRemaining({started:100,ends:1600,minutes:25},100),1500);
  assert.equal(v2.focusRemaining({started:100,ends:1600,minutes:25},1700),0);
});
test('marks deduplicate socket and history, and expand the day domain for early moments', () => {
  const mark = {ts:1800,kind:'win',note:null};
  assert.equal(v2.mergeMarks([mark],[mark]).length,1);
  const model = chart.chartModel('day',{start:0,bucket_minutes:5,points:[]},[],1000,[mark]);
  assert.equal(model.t0,0);
  assert.equal(v2.gestureLabel({ts:1600,gesture:'Pointing_Up',hand:'Right',action:'toggle_focus'},null,'ended'),'Focus ended');
});
