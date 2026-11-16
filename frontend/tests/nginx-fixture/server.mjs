import http from 'node:http';

const policy='dialogue-vpr-freetext-v1-application';
const sessionId='freetext-application-00000000-0000-0000-0000-000000000001';
const stats={createPosts:0,descriptionLength:0,sessionGets:0,eventStreams:[],probeConnections:0};
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const results=()=>Array.from({length:10},(_,index)=>({rank:index+1,candidate_id:`fixture-${index+1}`,latitude:40.41+index/10000,longitude:-3.7-index/10000,cosine_similarity:0.9-index/100}));
const events=[
 {id:'1',stage:'E0_qwen',state:'completed',message:'qwen E0: completed'},
 {id:'2',stage:'E0_crosstext2loc',state:'running',message:'crosstext2loc E0: running'},
 {id:'3',stage:'E0_crosstext2loc',state:'completed',message:'crosstext2loc E0: completed'},
 {id:'4',stage:'E0',state:'waiting_user',message:'E0 persistido; espera respuesta.'},
];

function json(response,status,body){response.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});response.end(JSON.stringify(body));}
function session(status){return{schema_version:'1.0',contract_version:'atlas-dialogue-freetext-application-session-public-v1',session_id:sessionId,policy_id:policy,status,turns:[],stage_snapshots:[{stage:'E0',gallery_id:'madrid-50m',candidate_count:253,results:results()}],current_question:status==='waiting_user'?{turn_index:1,question_id:'fixture-question-1',question:'¿Ves una fuente en el centro?',question_sha256:'a'.repeat(64)}:null,updated_at_utc:'2026-11-16T00:00:00Z'};}
async function body(request){let value='';for await(const chunk of request)value+=chunk;return value?JSON.parse(value):{};}
function sse(response,event){response.write(`id: ${event.id}\nevent: session\ndata: ${JSON.stringify(event)}\n\n`);}

const server=http.createServer(async(request,response)=>{
 const url=new URL(request.url,'http://api');
 if(url.pathname==='/api/v1/dialogue-freetext/nginx-probe'){
  stats.probeConnections+=1;response.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-cache','X-Accel-Buffering':'no'});response.write('event: probe\ndata: first\n\n');await delay(180);response.write(': keepalive\n\n');await delay(180);response.end('event: probe\ndata: last\n\n');return;
 }
 if(url.pathname==='/api/v1/dialogue-freetext/test-stats'){json(response,200,stats);return;}
 if(url.pathname==='/api/v1/capabilities'){json(response,200,{schema_version:'1.0',api_version:'v3-experimental',retrievers:[{id:'crosstext2loc',available:true}],galleries:[{gallery_id:'madrid-50m',candidate_count:253}],processing_modes:[{id:'no_llm',available:true,variant:'es_original'},{id:'with_llm',available:false,variant:'en_cartographic'}],search_area:{region_id:'D004',crs:'EPSG:4326',bbox:{south:40.4,north:40.43,west:-3.72,east:-3.68}},pipeline_progress:{stages:[{id:'freetext',available:true}]}});return;}
 if(url.pathname==='/api/v1/dialogue/queries'){json(response,200,{available:false,queries:[],adaptive_sessions:[]});return;}
 if(url.pathname==='/api/v1/dialogue/variants'){json(response,200,{schema_version:'1.0',contract_version:'atlas-description-variants-v1',variants:[]});return;}
 if(url.pathname==='/api/v1/dialogue-freetext/pilots'){json(response,200,{contract_version:'atlas-dialogue-freetext-policy-catalogue-v1',policies:[{policy_id:policy,available:true,enabled:true}]});return;}
 if(url.pathname==='/api/v1/dialogue-freetext/pilot'){json(response,404,{error:{code:'NOT_FOUND',message:'Sin piloto histórico'}});return;}
 if(url.pathname==='/api/v1/dialogue-freetext/sessions'&&request.method==='POST'){
  const payload=await body(request);stats.createPosts+=1;stats.descriptionLength=payload.description_es?.length||0;json(response,201,session('running'));return;
 }
  if(url.pathname===`/api/v1/dialogue-freetext/sessions/${sessionId}/events`){json(response,200,{events:stats.eventStreams.length===0?[]:stats.eventStreams.length===1?events.slice(0,2):events});return;}
 if(url.pathname===`/api/v1/dialogue-freetext/sessions/${sessionId}`){stats.sessionGets+=1;json(response,200,session(stats.sessionGets<2?'running':'waiting_user'));return;}
 if(url.pathname===`/api/v1/dialogue-freetext/sessions/${sessionId}/events/stream`){
  const after=url.searchParams.get('after');stats.eventStreams.push({after});response.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-cache','X-Accel-Buffering':'no'});
  if(!after){sse(response,events[0]);await delay(120);response.write(': keepalive\n\n');await delay(120);sse(response,events[1]);response.socket.destroy();return;}
  if(after==='2'){await delay(80);sse(response,events[2]);await delay(80);sse(response,events[3]);response.end();return;}
  response.end();return;
 }
 json(response,404,{error:{code:'NOT_FOUND',message:'Fixture endpoint not found'}});
});

server.listen(8000,'0.0.0.0');
