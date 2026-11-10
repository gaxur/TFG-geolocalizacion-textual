"""Aplicación ligera DialogueVPR; los modelos se cargan solo en workers secuenciales."""
from __future__ import annotations
from contextlib import asynccontextmanager
import asyncio
import json
import os
from pathlib import Path
from fastapi import FastAPI
from .dialogue_executor import SequentialDialogueExecutor
from .dialogue_sessions import DialogueSessionService
from .routes.dialogue import router as dialogue_router
ROOT=Path(__file__).resolve().parents[2]
@asynccontextmanager
async def lifespan(app:FastAPI):
    executor=SequentialDialogueExecutor(qwen_model=Path(os.environ['ATLAS_QWEN_MODEL_PATH']),runtime_config=Path(os.environ.get('ATLAS_RUNTIME_CONFIG',ROOT/'config/madrid_f46_retriever.json')),region_config=Path(os.environ.get('ATLAS_REGION_CONFIG',ROOT/'config/madrid.yaml')),f3_bundle=Path(os.environ['ATLAS_DIALOGUE_F3_BUNDLE']),clip_weights=Path(os.environ['CLIP_WEIGHTS_PATH']),cvg_utils_sha256=os.environ['ATLAS_CVG_UTILS_SHA256'],ollama_ps_url=os.environ.get('ATLAS_OLLAMA_PS_URL','http://host.docker.internal:11434/api/ps'))
    app.state.dialogue_service=DialogueSessionService(cohort_path=Path(os.environ['ATLAS_DIALOGUE_COHORT_PATH']),session_root=Path(os.environ['ATLAS_DIALOGUE_SESSION_ROOT']),image_root=Path(os.environ['ATLAS_DIALOGUE_IMAGE_ROOT']),executor=executor,completed_query_ids=tuple(x.strip() for x in os.environ.get('ATLAS_DIALOGUE_COMPLETED_QUERY_IDS','H26').split(',') if x.strip()),authorization_path=Path(os.environ['ATLAS_DIALOGUE_AUTHORIZATION_PATH']))
    app.state.dialogue_gate=asyncio.Lock()
    app.state.dialogue_variants=json.loads(Path(os.environ['ATLAS_DIALOGUE_VARIANTS_PATH']).read_text())
    yield
app=FastAPI(title='Atlas DialogueVPR',version='1.0',lifespan=lifespan);app.include_router(dialogue_router)
@app.get('/api/v1/health/live')
async def live():return {'status':'ok','service':'atlas-dialogue-api'}
@app.get('/api/v1/health/ready')
async def ready():return {'status':'ready','runtime':'dialogue-sequential'}
@app.get('/api/v1/dialogue/variants')
async def variants():return app.state.dialogue_variants
@app.get('/api/v1/capabilities')
async def capabilities():return {'schema_version':'1.0','api_version':'v3-experimental','retrievers':[{'id':'crosstext2loc','available':False,'scores_are_probabilities':False}],'processing_modes':[{'id':'no_llm','available':False,'variant':'es_original'},{'id':'with_llm','available':False,'variant':'en_cartographic','experimental':True}],'postprocessing_capabilities':[],'pipeline_progress':{'transport':'none','endpoint_template':None,'stages':[{'id':'llm','available':True},{'id':'crosstext2loc','available':True},{'id':'vlm','available':False},{'id':'dialoguevpr','available':True}]},'galleries':[{'gallery_id':'madrid-50m','candidate_count':253}],'search_area':{'region_id':'madrid_pilot','crs':'EPSG:4326','bbox':{'north':40.42,'south':40.412,'east':-3.699,'west':-3.709}},'supported_languages':{'policy_status':'experimental','accepted_codes':['es']}}
