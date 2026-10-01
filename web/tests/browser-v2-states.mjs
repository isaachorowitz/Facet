// Continue after browser-v2.mjs in the same managed fixture page.
async (page) => {
  const fixture = await (await page.request.get('http://127.0.0.1:5178/tests/v2.fixture.json')).json();
  const send = async message => page.evaluate(detail => window.dispatchEvent(new CustomEvent('facet-fixture', {detail})), message);
  const check = (value, message) => { if (!value) throw new Error(message); };
  const now = Date.now()/1000;
  const session = {started:now-300,ends:now+1200,minutes:25};
  await send({type:'focus',data:{state:'started',session}});
  await page.getByRole('button',{name:/End focus/}).waitFor();
  await send({type:'focus',data:{state:'ended',session}});
  await send({type:'gesture',data:{ts:Date.now()/1000,gesture:'Pointing_Up',hand:'Right',action:'toggle_focus'}});
  await page.locator('.gesture-label').filter({hasText:'Focus ended'}).waitFor();
  const focusEnded = await page.locator('.gesture-label').last().textContent();
  await send({type:'face_touch',data:{ts:Date.now()/1000,count_last_hour:4}});
  await page.locator('.touch-flash').waitFor();
  const touchCount = await page.locator('.touch-count').textContent();
  await send({...fixture.live,hands:[],caption:null});
  await page.waitForTimeout(450);
  check(await page.locator('.hand-overlay circle').count() === 0, 'Hands did not fade away');
  await send({...fixture.live,caption:null});
  await page.waitForTimeout(400);
  const markBox = await page.locator('.chart-mark').first().boundingBox(), plotBox = await page.locator('.plot').boundingBox();
  await page.mouse.move(markBox.x+markBox.width/2,plotBox.y+plotBox.height*.75);
  await page.getByRole('tooltip').waitFor();
  const bucketTooltip = await page.getByRole('tooltip').textContent();
  check(bucketTooltip.includes('Good moment') && bucketTooltip.includes('A clear start') && bucketTooltip.includes('Stress'), 'Bucket marks are missing');
  await page.getByRole('button',{name:'Story',exact:true}).click();
  await page.getByRole('dialog').waitFor();
  await page.locator('.story-backdrop').click({position:{x:10,y:10}});
  await page.getByRole('dialog').waitFor({state:'hidden'});
  // Advance the caption age, without waiting or changing a real backend session.
  await page.evaluate(() => { const original = Date.now; Date.now = () => original()+41000; });
  await page.waitForTimeout(1100);
  const fallback = await page.locator('.sentence').textContent();
  check(!fallback.includes('Narrator') && fallback.includes('Stress is low.'), 'Caption did not expire to the generated sentence');
  await page.emulateMedia({reducedMotion:'reduce'});
  const virtualNow = await page.evaluate(() => Date.now()/1000);
  await send({type:'caption',data:{ts:virtualNow,text:'Every word appears together when motion is reduced.'}});
  await page.waitForTimeout(100);
  const reducedCaption = await page.locator('.sentence p [aria-hidden="true"]').textContent();
  await send({type:'gesture',data:{ts:Date.now()/1000,gesture:'ILoveYou',hand:'Left',action:null}});
  await page.waitForTimeout(100);
  const reducedTransform = await page.locator('.gesture-celebration').last().evaluate(el => getComputedStyle(el).transform);
  const reducedBurst = await page.locator('.gesture-burst:visible').count();
  check(reducedCaption.includes('Every word appears together') && reducedTransform === 'none' && reducedBurst === 0, `Reduced motion behavior failed: ${JSON.stringify({reducedCaption,reducedTransform,reducedBurst})}`);
  // Reload as a v1 backend. New endpoints deliberately return 404; all writes stay intercepted.
  const legacy = JSON.parse(JSON.stringify(fixture));
  delete legacy.live.view; delete legacy.live.hands; delete legacy.live.wellness; delete legacy.live.caption; delete legacy.live.focus_session; delete legacy.live.posture.stale;
  delete legacy.summary.marks; delete legacy.summary.sips; delete legacy.summary.face_touches; delete legacy.summary.eyes_breaks_taken; delete legacy.summary.eyes_breaks_due; delete legacy.summary.focus_sessions;
  for (const point of legacy.timeline.points) delete point.marks;
  await page.route('http://127.0.0.1:5178/api/**', route => {
    const path = '/' + route.request().url().split('?')[0].split('/').slice(3).join('/');
    const payload = { '/api/timeline':legacy.timeline, '/api/summary':legacy.summary, '/api/speech':[] }[path];
    return route.fulfill({status:payload ? 200 : 404,contentType:'application/json',body:JSON.stringify(payload ?? {})});
  });
  await page.addInitScript(fixture => {
    window.WebSocket = class extends EventTarget {
      static OPEN = 1; readyState = 1; onopen = null; onmessage = null; onclose = null; onerror = null;
      constructor() { super(); setTimeout(() => { this.onopen?.({}); this.onmessage?.({data:JSON.stringify(fixture.hello)}); this.onmessage?.({data:JSON.stringify(fixture.live)}); },30); }
      send() {} close() { this.readyState = 3; }
    };
  }, legacy);
  await page.reload();
  await page.getByRole('button',{name:'Story',exact:true}).waitFor();
  await page.waitForTimeout(1100);
  const legacySentence = await page.locator('.sentence').textContent();
  const legacyStats = await page.locator('.stats').textContent();
  await page.getByRole('button',{name:'Focus 25',exact:true}).click();
  await page.locator('.toast').filter({hasText:'Focus is unavailable'}).waitFor();
  await page.getByRole('button',{name:'Story',exact:true}).click();
  await page.locator('.story-empty').filter({hasText:'not available yet'}).waitFor();
  const unavailable = await page.locator('.story-empty').textContent();
  check(legacySentence.includes('Stress is low.') && legacyStats.includes('Sips today–') && unavailable.includes('not available yet'), 'Legacy fallbacks failed');
  await page.keyboard.press('Escape');
  return { focusEnded,touchCount,bucketTooltip,fallback,reducedCaption,reducedTransform,reducedBurst,legacySentence,legacyStats,unavailable };
}
