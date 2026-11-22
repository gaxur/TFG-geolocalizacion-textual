import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';

const base=process.env.APP_BASE_URL||'http://frontend:8080';
const profile=fs.mkdtempSync(`${os.tmpdir()}/appflow-`);
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const browser=spawn(process.env.CHROME_PATH||'/usr/bin/chromium',['--headless=new','--no-sandbox','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore'});
let ws;
try{
  for(let i=0;i<100&&!fs.existsSync(`${profile}/DevToolsActivePort`);i++)await delay(100);
  const port=fs.readFileSync(`${profile}/DevToolsActivePort`,'utf8').split('\n')[0];
  const pages=await(await fetch(`http://127.0.0.1:${port}/json`)).json();
  ws=new WebSocket(pages.find(row=>row.type==='page').webSocketDebuggerUrl);
  await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}));
  let id=0;const pending=new Map();
  ws.addEventListener('message',event=>{const data=JSON.parse(event.data);if(data.id&&pending.has(data.id)){pending.get(data.id)(data);pending.delete(data.id)}});
  const send=(method,params={})=>new Promise(resolve=>{const call=++id;pending.set(call,resolve);ws.send(JSON.stringify({id:call,method,params}))});
  const evaluate=async expression=>(await send('Runtime.evaluate',{expression,returnByValue:true})).result.result.value;
  const screenshot=async path=>{const capture=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path,Buffer.from(capture.result.data,'base64'))};
  const waitFor=async expression=>{for(let i=0;i<200;i++){await delay(100);if(await evaluate(expression))return}throw new Error(`Timeout: ${expression}`)};
  await send('Page.enable');await send('Runtime.enable');await send('Page.navigate',{url:base});
  await waitFor(`Boolean(document.querySelector('#search-form button:not([disabled])')&&document.querySelector('.maplibregl-canvas'))`);
  const instance=await evaluate(`document.querySelector('#results-map').dataset.mapInstanceId`);
  await evaluate(`(()=>{const x=document.querySelector('#description');x.value='xx';x.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#search-form').requestSubmit()})()`);await delay(150);assert.equal(await evaluate(`Boolean(document.querySelector('#operation-modal')?.open)`),false);
  await evaluate(`(()=>{const x=document.querySelector('#description');x.value='Una plaza y una torre';x.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#search-form').requestSubmit()})()`);
  await waitFor(`document.querySelector('#operation-modal')?.open`);
  await evaluate(`document.querySelector('#operation-modal').dispatchEvent(new Event('cancel',{cancelable:true}))`);
  assert.equal(await evaluate(`document.querySelector('#operation-modal').open`),true);
  await waitFor(`document.querySelector('.operation-stages li:nth-child(2)')?.classList.contains('active')&&document.querySelector('#operation-modal')?.open&&document.querySelector('#results-map')?.dataset.mapCandidateCount==='0'`);
  assert.equal(await evaluate(`document.querySelector('.operation-stages li:first-child').classList.contains('done')`),true);
  await send('Page.reload');
  await waitFor(`document.querySelector('#results-map')?.dataset.mapCandidateCount==='10'&&Boolean(document.querySelector('[data-action="open-dialogue"]'))&&!document.querySelector('#operation-modal')?.open`);
  assert.equal(await evaluate(`Boolean(document.querySelector('#freetext-answer'))`),false);
  await evaluate(`document.querySelector('[data-action="open-dialogue"]').click()`);
  await waitFor(`Boolean(document.querySelector('#dialogue-modal')?.open&&document.querySelector('#freetext-answer'))`);
  for(let stage=0;stage<4;stage++){
    if(stage>0&&stage<3){await waitFor(`document.querySelector('#results-map')?.dataset.mapCandidateCount==='10'`);await waitFor(`!document.querySelector('#operation-modal')?.open`);await waitFor(`document.querySelector('[data-action="open-dialogue"]')?.textContent.includes('Refinar ubicación')`);await evaluate(`document.querySelector('[data-action="open-dialogue"]').click()`);}
    if(stage<3)await waitFor(`Boolean(document.querySelector('[data-freetext-stage="E${stage}"]')&&document.querySelector('#results-map')?.dataset.mapCandidateCount==='10')`);
    else{for(let i=0;i<100;i++){const current=await(await fetch(`${base}/api/v1/dialogue-freetext/sessions/dq-iterative-00000000-0000-0000-0000-000000000001`)).json();if(current.status==='completed'&&current.stage_snapshots.length===4)break;await delay(100);if(i===99)throw new Error('E3 terminal no persistido');}}
    assert.equal(await evaluate(`document.querySelector('#results-map').dataset.mapInstanceId`),instance);
    if(stage===0){await evaluate(`document.querySelector('[data-map-action="mode-3d"]').click()`);await delay(3500);assert.ok(Number(await evaluate(`document.querySelector('#results-map')?.dataset.mapBuilding3dRenderedFeatureCount`))>0,'no se renderizaron edificios 3D');await evaluate(`window.__atlasInspectMap(-3.7089496,40.4159601,18)`);await delay(3500);const metrics=JSON.parse(await evaluate(`JSON.stringify(document.querySelector('#results-map').dataset)`));console.log('MAP_3D_METRICS',metrics);assert.ok(Number(metrics.mapTreeSourceFeatureCount)>0,'la fuente no cargó árboles 3D');assert.equal(metrics.mapTreeExtrusionVisibility,'visible');assert.ok(Number(metrics.mapTree3dRenderedFeatureCount)>0,'no se renderizaron árboles 3D');await screenshot('/tmp/screenshots/frontend-after-desktop-3d.png');await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await screenshot('/tmp/screenshots/frontend-after-mobile-dialogue.png');await send('Emulation.clearDeviceMetricsOverride');}
    if(stage<3){
      await waitFor(`Boolean(document.querySelector('#freetext-answer'))`);assert.equal(await evaluate(`document.querySelector('.freetext-progress strong')?.textContent`),`Pregunta ${stage+1} de 3`);assert.equal(await evaluate(`Boolean(document.querySelector('[data-action=\"stop-dq-dialogue\"]'))`),true);
      await evaluate(`(()=>{const x=document.querySelector('#freetext-answer');x.value='Respuesta ${stage+1}';x.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#freetext-answer-form').requestSubmit()})()`);
      await waitFor(`document.querySelector('#operation-modal')?.open`);
      if(stage===1){await waitFor(`document.querySelector('.operation-stages li:nth-child(2)')?.classList.contains('active')&&document.querySelector('#operation-modal')?.open`);await send('Page.reload');}
    }
  }
  const terminal=await(await fetch(`${base}/api/v1/dialogue-freetext/sessions/dq-iterative-00000000-0000-0000-0000-000000000001`)).json();
  assert.equal(terminal.status,'completed');assert.deepEqual(terminal.stage_snapshots.map(row=>row.stage),['E0','E1','E2','E3']);assert.equal(terminal.current_question,null);assert.equal(terminal.turns.length,3);
  const counters=await(await fetch('http://api:8000/fixture/counters')).json();
  assert.equal(counters.creates,1);assert.equal(counters.answers,3);assert.ok(counters.gets>=3);assert.ok(counters.streams>=4);
  console.log('APP_FLOW_BROWSER_PASS');
}finally{ws?.close();browser.kill('SIGTERM')}
