import http from 'node:http';

const policy='dialogue-vpr-dq-pilot-v1';
const sessionId='dq-iterative-00000000-0000-0000-0000-000000000001';
const counters={creates:0,answers:0,gets:0,streams:0};
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
// Fixture UI cerca de árboles OSM reales; no representa una inferencia ni ground truth.
const rows=stage=>Array.from({length:10},(_,index)=>({rank:index+1,candidate_id:`MADP_MADRID_PILOT_GRID_V1_GA467049559FD_S050_L050_R${String(stage+1).padStart(4,'0')}_C${String(index+1).padStart(4,'0')}`,latitude:40.4157+stage/10000+index/100000,longitude:-3.709+index/10000,cosine_similarity:.9-index/100}));
let completedStage=-1,status='pending',targetStage=0,answers=[],events=[];
const event=(stage,state,message)=>{const row={id:String(events.length+1),stage,state,message,created_at_utc:new Date().toISOString()};events.push(row);return row};
const turns=()=>Array.from({length:Math.min(3,Math.max(0,completedStage+1))},(_,index)=>({index:index+1,question:`¿Qué rasgo visual distingue mejor las ubicaciones en la ronda ${index+1}?`,answer_literal:answers[index]??null}));
const session=()=>({schema_version:'1.0',contract_version:'atlas-dq-iterative-session-public-v1',session_id:sessionId,policy_id:policy,status,stop_reason:status==='completed'?'max_questions_reached_after_e3':status==='failed'?'runtime_error_no_retry':null,turns:turns(),current_question:status==='waiting_user'?{turn_index:completedStage+1,question_id:`q${completedStage+1}`,question:`¿Qué rasgo visual distingue mejor las ubicaciones en la ronda ${completedStage+1}?`,question_sha256:String(completedStage+1).repeat(64)}:null,stage_snapshots:Array.from({length:completedStage+1},(_,index)=>({stage:`E${index}`,gallery_id:'madrid-50m',candidate_count:253,ranking_sha256:String(index+1).repeat(64),results:rows(index)})),final_stage:completedStage>=0?`E${completedStage}`:null,updated_at_utc:new Date().toISOString()});
function json(response,code,document){response.writeHead(code,{'Content-Type':'application/json'});response.end(JSON.stringify(document))}
async function body(request){let value='';for await(const chunk of request)value+=chunk;return value?JSON.parse(value):{}}
function sse(response,row){response.write(`id: ${row.id}\nevent: session\ndata: ${JSON.stringify(row)}\n\n`)}
function runStage(stage,fail=false){targetStage=stage;status='running';event(`E${stage}`,'running',`E${stage} iniciado.`);setTimeout(()=>{if(fail){event(`E${stage}_qwen`,'failed',`qwen E${stage}: failed`);status='failed';event(`E${stage}`,'failed',`E${stage} falló; no se reintenta.`);return}event(`E${stage}_qwen`,'completed',`qwen E${stage}: completed`)},200);if(!fail){setTimeout(()=>event(`E${stage}_crosstext2loc`,'running',`crosstext2loc E${stage}: running`),900);setTimeout(()=>{event(`E${stage}_crosstext2loc`,'completed',`crosstext2loc E${stage}: completed`);completedStage=stage;status=stage===3?'completed':'waiting_user';event(`E${stage}`,status,stage===3?'Sesión completada.':`E${stage} persistido; espera respuesta.`)},1500)}}
function reset(){completedStage=-1;status='pending';targetStage=0;answers=[];events=[]}

http.createServer(async(request,response)=>{
 const url=new URL(request.url,'http://api');
 if(url.pathname==='/api/v1/health/live'){json(response,200,{status:'ok'});return}
 if(url.pathname==='/api/v1/health/ready'){json(response,200,{status:'ready'});return}
 if(url.pathname==='/api/v1/capabilities'){json(response,200,{schema_version:'1.0',api_version:'v3-experimental',retrievers:[{id:'crosstext2loc',available:true}],processing_modes:[{id:'no_llm',available:false,variant:'es_original'},{id:'with_llm',available:true,variant:'en_cartographic',resident:true}],galleries:[{gallery_id:'madrid-50m',candidate_count:253}],search_area:{region_id:'madrid_pilot',crs:'EPSG:4326',bbox:{north:40.42,south:40.412,east:-3.699,west:-3.709}},pipeline_progress:{stages:[{id:'freetext',available:true}]}});return}
 if(url.pathname==='/api/v1/dialogue-freetext/pilots'){json(response,200,{contract_version:'atlas-dialogue-freetext-policy-catalogue-v1',policies:[{policy_id:policy,available:true,enabled:true,maximum_questions:3,execution_readiness:{runtime_connected:true,artifacts_ready:true,authorization_ready:true,translation_ready:true,quality_gate_ready:true}}]});return}
 if(url.pathname==='/api/v1/dialogue-freetext/pilot'){json(response,404,{error:{code:'NOT_FOUND',message:'Sin piloto'}});return}
 if(url.pathname==='/api/v1/dialogue-freetext/sessions'&&request.method==='POST'){await body(request);counters.creates+=1;reset();runStage(0);json(response,200,session());return}
 if(url.pathname===`/api/v1/dialogue-freetext/sessions/${sessionId}/answers`&&request.method==='POST'){const payload=await body(request);counters.answers+=1;answers[payload.turn_index-1]=payload.answer_literal;runStage(payload.turn_index,payload.answer_literal==='FALLAR');json(response,200,session());return}
 if(url.pathname===`/api/v1/dialogue-freetext/sessions/${sessionId}`){counters.gets+=1;json(response,200,session());return}
 if(url.pathname===`/api/v1/dialogue-freetext/sessions/${sessionId}/events`){json(response,200,{events});return}
 if(url.pathname===`/api/v1/dialogue-freetext/sessions/${sessionId}/events/stream`){counters.streams+=1;const after=url.searchParams.get('after');let cursor=after?Number(after):0;response.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-cache','X-Accel-Buffering':'no'});for(let tick=0;tick<100;tick++){for(const row of events.slice(cursor)){sse(response,row);cursor=Number(row.id)}if(['waiting_user','completed','failed','unknown'].includes(status)&&cursor>=events.length){response.end();return}await delay(25)}response.end();return}
 if(url.pathname==='/fixture/counters'){json(response,200,counters);return}
 json(response,404,{error:{code:'NOT_FOUND',message:'Fixture endpoint not found'}})
}).listen(8000,'0.0.0.0');
