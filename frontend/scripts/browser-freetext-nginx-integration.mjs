import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';

const base=process.env.FREETEXT_NGINX_TEST_URL||'http://127.0.0.1:18080';
const chrome=process.env.CHROME_PATH||'/usr/bin/chromium';
const profile=fs.mkdtempSync(`${os.tmpdir()}/atlas-freetext-nginx-`);
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const browser=spawn(chrome,['--headless=new','--no-sandbox','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore'});
let ws;

try{
 for(let i=0;i<100&&!fs.existsSync(`${profile}/DevToolsActivePort`);i++)await delay(100);
 assert.ok(fs.existsSync(`${profile}/DevToolsActivePort`),'Chromium no publicó DevToolsActivePort');
 const port=fs.readFileSync(`${profile}/DevToolsActivePort`,'utf8').split('\n')[0];
 const pages=await(await fetch(`http://127.0.0.1:${port}/json`)).json();
 ws=new WebSocket(pages.find(page=>page.type==='page').webSocketDebuggerUrl);
 await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}));
 let callId=0;const pending=new Map();
 ws.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id&&pending.has(message.id)){pending.get(message.id)(message);pending.delete(message.id);}});
 const send=(method,params={})=>new Promise(resolve=>{const id=++callId;pending.set(id,resolve);ws.send(JSON.stringify({id,method,params}));});
 const evaluate=async expression=>{const message=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(message.result.exceptionDetails)throw new Error(message.result.exceptionDetails.text);return message.result.result.value;};
 await send('Page.enable');await send('Runtime.enable');await send('Page.navigate',{url:base});
 for(let i=0;i<100&&!await evaluate('Boolean(document.querySelector("#description")&&document.querySelector("#freetext-start:not([disabled])"))');i++)await delay(100);
 assert.equal(await evaluate('Boolean(document.querySelector("#freetext-start:not([disabled])"))'),true,'la política operacional no llegó a estar disponible');
 const probe=await evaluate(`(async()=>{const response=await fetch('/api/v1/dialogue-freetext/nginx-probe');const reader=response.body.getReader(),decoder=new TextDecoder(),chunks=[],started=performance.now();for(;;){const {done,value}=await reader.read();if(done)break;chunks.push({at:performance.now()-started,text:decoder.decode(value)});}return chunks;})()`);
 assert.ok(probe.length>=2,`Nginx agrupó todo el SSE: ${JSON.stringify(probe)}`);
 assert.match(probe.map(row=>row.text).join(''),/: keepalive/);
 assert.ok(probe[0].at<100&&probe[1].at>=100,'el primer evento no llegó incrementalmente antes del keepalive');
 const ui=await evaluate(`(()=>{const input=document.querySelector('#description');input.value='x'.repeat(2400);input.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#freetext-start').click();return{maxLength:input.maxLength,counter:document.querySelector('#char-count').textContent};})()`);
 assert.equal(ui.maxLength,2400);assert.match(ui.counter,/2[.\s]?400 \/ 2[.\s]?400/);
 let reconciled=false;
 for(let i=0;i<120;i++){await delay(100);reconciled=await evaluate(`Boolean(document.querySelector('#freetext-answer')&&document.querySelector('[data-freetext-stage="E0"]'))`);if(reconciled)break;}
 assert.ok(reconciled,'la UI no reconcilió la desconexión SSE mediante GET');
 const stats=await(await fetch(`${base}/api/v1/dialogue-freetext/test-stats`)).json();
 assert.equal(stats.createPosts,1,'la reconciliación no debe repetir el POST de creación');
 assert.equal(stats.descriptionLength,2400);
 assert.ok(stats.sessionGets>=2,'faltaron GET de reconciliación tras desconexión');
 assert.deepEqual(stats.eventStreams.map(row=>row.after),[null,'2'],'el segundo SSE debe reanudar desde el último cursor');
 assert.equal(stats.probeConnections,1);
 console.log('FREETEXT_NGINX_INTEGRATION_PASS');
}finally{
 ws?.close();
 if(browser.exitCode===null){const exited=new Promise(resolve=>browser.once('exit',resolve));browser.kill('SIGTERM');await Promise.race([exited,delay(3000)]);if(browser.exitCode===null){browser.kill('SIGKILL');await Promise.race([exited,delay(3000)]);}}
 for(let attempt=0;attempt<10;attempt++){try{fs.rmSync(profile,{recursive:true,force:true,maxRetries:10,retryDelay:100});break}catch{await delay(200);}}
}
