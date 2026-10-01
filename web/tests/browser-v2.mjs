// Run this function through the managed playwright-isolated browser_run_code tool.
// All API methods, video, and WebSockets are fixtures. No request reaches the live backend.
async (page) => {
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  const fixtureResponse = await page.request.get('http://127.0.0.1:5178/tests/v2.fixture.json');
  const fixture = await fixtureResponse.json();
  const day = await page.evaluate(() => { const d = new Date(); return { start: new Date(d.getFullYear(),d.getMonth(),d.getDate()).getTime()/1000,
    date: `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}` }; });
  const delta = day.start - fixture.timeline.start;
  const shift = value => { if (!value || typeof value !== 'object') return; for (const [key, child] of Object.entries(value)) {
    if (['ts','t','start','started','ends','first_seen','last_seen','generated_at'].includes(key) && typeof child === 'number') value[key] += delta;
    else if (key === 'date') value[key] = day.date; else shift(child);
  }};
  shift(fixture);
  const now = Date.now() / 1000;
  fixture.caption.ts = now; fixture.live.caption.ts = now; fixture.hello.latest.face.ts = now;
  const writes = [], errors = [];
  let focus = null;
  page.on('pageerror', error => errors.push(error.message));
  await page.route('http://127.0.0.1:5178/api/**', async route => {
    const path = '/' + route.request().url().split('?')[0].split('/').slice(3).join('/'), method = route.request().method();
    if (method !== 'GET') writes.push({ path, method, body: route.request().postData() });
    let result;
    if (path === '/api/timeline') result = fixture.timeline;
    else if (path === '/api/summary') result = fixture.summary;
    else if (path === '/api/marks') result = fixture.marks;
    else if (path === '/api/captions') result = [fixture.caption];
    else if (path === '/api/speech') result = [];
    else if (path === '/api/recap') result = method === 'POST' ? { ...fixture.recap, text: 'Regenerated: a quiet day with a clear rhythm.', generated_at: Date.now() / 1000 } : fixture.recap;
    else if (path === '/api/focus') { focus = focus ? null : { started: Date.now() / 1000, ends: Date.now() / 1000 + 1500, minutes: 25 }; result = focus; }
    else return route.fulfill({ status: 404, body: '{}' });
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(result) });
  });
  await page.route('**/video.mjpg?*', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="600"><defs><radialGradient id="a"><stop stop-color="#344347"/><stop offset="1" stop-color="#101517"/></radialGradient></defs><rect width="720" height="600" fill="url(#a)"/><ellipse cx="360" cy="245" rx="86" ry="108" fill="#62696a"/><path d="M170 600v-45c0-200 380-200 380 0v45" fill="#404f52"/></svg>' }));
  await page.addInitScript(fixture => {
    window.WebSocket = class extends EventTarget {
      static OPEN = 1; static CLOSED = 3; readyState = 1;
      onopen = null; onmessage = null; onclose = null; onerror = null;
      constructor() { super(); this.receive = event => this.onmessage?.({ data: JSON.stringify(event.detail) }); window.addEventListener('facet-fixture', this.receive);
        setTimeout(() => { this.onopen?.({}); this.onmessage?.({ data: JSON.stringify(fixture.hello) }); this.onmessage?.({ data: JSON.stringify(fixture.live) }); }, 30); }
      send() {} close() { this.readyState = 3; window.removeEventListener('facet-fixture', this.receive); }
    };
  }, fixture);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto('http://127.0.0.1:5178');
  await page.locator('.stats').getByText('Sips today').waitFor();
  await page.waitForTimeout(1800);
  const layouts = [];
  for (const [width, height] of [[1280,720], [1440,900], [1920,1080], [2560,1440]]) {
    await page.setViewportSize({ width, height });
    await page.waitForTimeout(150);
    layouts.push(await page.evaluate(() => {
      const bounds = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom }; };
      return { width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,
        header:bounds('header'),now:bounds('.now'),hero:bounds('.hero'),sentence:bounds('.sentence'),lower:bounds('.lower'),day:bounds('.day'),stats:bounds('.stats'),
        dayPaddingBottom:getComputedStyle(document.querySelector('.day')).paddingBottom,
        clippedStats:[...document.querySelectorAll('.stats > div')].filter(e => e.getBoundingClientRect().bottom > document.querySelector('.stats').getBoundingClientRect().bottom + 1).length,
        hands:document.querySelectorAll('.hand-overlay circle').length };
    }));
  }
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.evaluate(() => document.documentElement.dataset.shell = 'mac');
  const macPadding = await page.locator('header').evaluate(el => getComputedStyle(el).paddingLeft);
  await page.getByRole('button', { name:'Focus 25',exact:true }).click();
  await page.getByRole('button', { name:/End focus/ }).waitFor();
  const cool = await page.locator('#app').evaluate(el => el.classList.contains('focusing'));
  await page.getByRole('button', { name:/End focus/ }).click();
  await page.getByRole('button', { name:'Focus 25',exact:true }).waitFor();
  await page.getByRole('button', { name:'Story',exact:true }).click();
  await page.getByRole('dialog').waitFor();
  await page.getByRole('button', { name:'Regenerate',exact:true }).click();
  await page.getByRole('dialog').getByText('Regenerated: a quiet day with a clear rhythm.', {exact:true}).first().waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('dialog').waitFor({state:'hidden'});
  const restoredFocus = await page.getByRole('button', { name:'Story',exact:true }).evaluate(el => document.activeElement === el);
  const labels = [];
  for (const [gesture, action] of [['Thumb_Up','mark_good'],['Thumb_Down','mark_rough'],['Victory','mark_win'],['Pointing_Up','toggle_focus'],['Open_Palm',null],['Wave','hello'],['ILoveYou',null]]) {
    await page.evaluate(data => window.dispatchEvent(new CustomEvent('facet-fixture',{detail:{type:'gesture',data}})), { ts:Date.now()/1000, gesture,hand:'Right',action });
    await page.waitForTimeout(100);
    labels.push(await page.locator('.gesture-label').last().textContent());
  }
  await page.evaluate(live => window.dispatchEvent(new CustomEvent('facet-fixture',{detail:{...live,posture:{...live.posture,visible:false,stale:true,skeleton:{}}}})), fixture.live);
  await page.locator('.pscore .st').filter({hasText:'holding'}).waitFor();
  const held = await page.locator('.figure.holding .bone').count();
  await page.evaluate(live => window.dispatchEvent(new CustomEvent('facet-fixture',{detail:{...live,posture:{...live.posture,visible:false,stale:false,skeleton:{}}}})), fixture.live);
  await page.locator('.figure').getByText('Your posture will return').waitFor();
  await page.evaluate(ts => window.dispatchEvent(new CustomEvent('facet-fixture',{detail:{type:'caption',data:{ts,text:'Expired caption'}}})), Date.now()/1000 - 41);
  // An older caption cannot replace a newer one; expire the current caption with a virtual clock instead in a later scenario.
  await page.locator('.chart-mark').first().hover();
  await page.getByRole('tooltip').waitFor();
  const tooltip = await page.getByRole('tooltip').textContent();
  const check = (value, message) => { if (!value) throw new Error(message); };
  check(layouts.every(l => l.scrollWidth === l.width && l.scrollHeight === l.height && l.clippedStats === 0 && l.hands === 42), 'Viewport or hand layout failed');
  check(layouts.every(l => l.stats.bottom <= l.day.bottom - parseFloat(l.dayPaddingBottom) + 1), 'Stats exceed padded day card');
  check(macPadding === '76px' && cool && restoredFocus && held > 0, 'Focus, mac shell, or posture behavior failed');
  check(labels.join('|') === 'Good moment marked|Rough moment marked|Win marked|Focus started|Hello there|Hey!|Love you', 'Gesture labels failed');
  check(tooltip.includes('A clear start') && errors.length === 0 && writes.length === 3, 'Tooltip, runtime, or mock write checks failed');
  return { layouts,macPadding,cool,restoredFocus,labels,held,tooltip,writes,errors };
}
