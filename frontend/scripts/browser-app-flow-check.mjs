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
  const waitFor=async expression=>{for(let i=0;i<200;i++){await delay(100);if(await evaluate(expression))return}throw new Error(`Timeout: ${expression}`)};
  await send('Page.enable');await send('Runtime.enable');await send('Page.navigate',{url:base});
  await waitFor(`Boolean(document.querySelector('#search-form button:not([disabled])')&&document.querySelector('.maplibregl-canvas'))`);
  const instance=await evaluate(`document.querySelector('#results-map').dataset.mapInstanceId`);
  await evaluate(`(()=>{const x=document.querySelector('#description');x.value='Una plaza y una torre';x.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#search-form').requestSubmit()})()`);
  await waitFor(`document.querySelector('.freetext-progress small')?.textContent.includes('qwen E0: completed')&&document.querySelectorAll('.result-card').length===0`);
  await send('Page.reload');
  await waitFor(`document.querySelectorAll('.result-card').length===10&&Boolean(document.querySelector('#freetext-answer'))`);
  for(let stage=0;stage<4;stage++){
    await waitFor(`Boolean(document.querySelector('[data-freetext-stage="E${stage}"]')&&document.querySelectorAll('.result-card').length===10)`);
    assert.equal(await evaluate(`document.querySelector('#results-map').dataset.mapInstanceId`),instance);
    if(stage<3){
      await waitFor(`Boolean(document.querySelector('#freetext-answer'))`);
      await evaluate(`(()=>{const x=document.querySelector('#freetext-answer');x.value='Respuesta ${stage+1}';x.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#freetext-answer-form').requestSubmit()})()`);
      if(stage===1){await waitFor(`document.querySelector('.freetext-progress small')?.textContent.includes('crosstext2loc E2: running')`);await send('Page.reload');}
    }
  }
  await waitFor(`!document.querySelector('#freetext-answer')`);
  await send('Page.reload');
  await waitFor(`document.querySelectorAll('[data-freetext-stage]').length===4`);
  assert.equal(await evaluate(`document.querySelectorAll('[data-freetext-stage]').length`),4);
  await waitFor(`Boolean(document.querySelector('[data-action="new-freetext-search"]'))`);
  await evaluate(`document.querySelector('[data-action="new-freetext-search"]').click()`);
  await waitFor(`document.querySelectorAll('[data-freetext-stage]').length===0&&Boolean(document.querySelector('#description:not([disabled])'))`);
  assert.equal(await evaluate(`document.querySelector('#results-map').dataset.mapInstanceId`),instance);
  await evaluate(`(()=>{const x=document.querySelector('#description');x.value='Otra descripción de prueba';x.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#search-form').requestSubmit()})()`);
  await waitFor(`document.querySelectorAll('.result-card').length===10&&Boolean(document.querySelector('#freetext-answer'))`);
  const preserved=await evaluate(`JSON.stringify([...document.querySelectorAll('.result-card .card-title h3')].map(x=>x.textContent))`);
  await evaluate(`(()=>{const x=document.querySelector('#freetext-answer');x.value='FALLAR';x.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#freetext-answer-form').requestSubmit()})()`);
  await waitFor(`document.querySelector('.freetext-status')?.textContent.includes('Fallida')`);
  assert.equal(await evaluate(`JSON.stringify([...document.querySelectorAll('.result-card .card-title h3')].map(x=>x.textContent))`),preserved);
  const counters=await(await fetch('http://api:8000/fixture/counters')).json();
  assert.equal(counters.creates,2);assert.equal(counters.answers,4);assert.ok(counters.gets>=3);assert.ok(counters.streams>=4);
  console.log('APP_FLOW_BROWSER_PASS');
}finally{ws?.close();browser.kill('SIGTERM')}
