from pathlib import Path
from types import SimpleNamespace
import threading

from backend.atlas_api.dialogue_freetext_executor import FreeTextRuntimeExecutor,observable_transcript


class Qwen:
    metadata = SimpleNamespace(model_id="Qwen/Qwen3-8B", revision="b968826d9c46dd6066d109eabc6255188de91218")
    def __init__(self): self.calls=0;self.closed=False
    def generate_prompt(self,prompt,_config): self.calls+=1;return SimpleNamespace(text="I am in a wide plaza.",raw_output="I am in a wide plaza.",duration_ms=1.0)
    def close(self): self.closed=True


class Retriever:
    def __init__(self): self.calls=0;self.closed=False
    def retrieve_many(self,**kwargs):
        self.calls+=1;rows=[{"rank":i,"candidate_id":f"c{i:03d}","latitude":40.0,"longitude":-3.0,"cosine_similarity":1-i/1000} for i in range(1,254)];return {"schema_version":"1.0","contract_version":"crosstext2loc-retrieval-response-v1","query":{"query_id":kwargs["query_id"],"text":kwargs["text"],"language":kwargs["language"]},"model":{"name":"CLIP-L/14@336","checkpoint_sha256":"a"*64},"retrievals":[{"gallery_id":"madrid-50m","visual_dataset_id":"visual","embedding_dataset_id":"embedding","gallery_count":253,"requested_k":253,"effective_k":253,"ranking_method":"exhaustive_cosine","tie_break":"candidate_id_ascending","results":rows}],"timings_ms":{"text_encoding":1.0,"ranking_by_gallery":{"madrid-50m":1.0},"total":2.0}}
    def close(self): self.closed=True


def executor(qwen,retriever):
    value=FreeTextRuntimeExecutor.__new__(FreeTextRuntimeExecutor);value.resident_models=True;value._resident_qwen=None;value._resident_retriever=None;value._resident_gallery_ids=();value._resident_gated_models=set();value._resident_lock=threading.RLock();value._qwen_factory=lambda:qwen;value._retriever_factory=lambda _ids:retriever;value._identity={'checkpoint_sha256':'a'*64,'madrid_50m_visual_dataset_id':'visual','madrid_50m_embedding_dataset_id':'embedding'};value.progress_callback=None;value._gate=lambda _root,_label:None;return value


def test_resident_models_load_once_reuse_and_close(tmp_path):
    qwen,retriever=Qwen(),Retriever();value=executor(qwen,retriever);gates=[];value._gate=lambda _root,label:gates.append(label)
    transcript='[DESCRIPCIÓN ORIGINAL]\nEstoy en una plaza amplia.';first=value._resident_transform(stage="E0",transcript=transcript,prompt="prompt",root=tmp_path);second=value._resident_transform(stage="E1",transcript=transcript,prompt="prompt 2",root=tmp_path)
    ranking0=value._resident_retrieve(stage="E0",query_id="q",text="English",root=tmp_path);ranking1=value._resident_retrieve(stage="E1",query_id="q",text="English 2",root=tmp_path)
    assert "runtime_telemetry" not in first and "runtime_telemetry" not in ranking0
    assert len(ranking0["results"])==253 and ranking0==ranking1
    assert __import__('json').loads((tmp_path/'e0-qwen-runtime.json').read_text())['cache_hit'] is False
    assert __import__('json').loads((tmp_path/'e1-qwen-runtime.json').read_text())['cache_hit'] is True
    assert __import__('json').loads((tmp_path/'e1-crosstext2loc-runtime.json').read_text())['cache_hit'] is True
    assert qwen.calls==2 and retriever.calls==2
    assert gates==['resident-qwen-load','resident-crosstext2loc-load']
    value.close();assert qwen.closed and retriever.closed


def test_observable_transcript_excludes_turn_numbers_and_questions():
    transcript='[DESCRIPCIÓN ORIGINAL]\nVeo 2 torres.\n[TURNO 1 — PREGUNTA]\n¿Ves una iglesia?\n[TURNO 1 — RESPUESTA LITERAL]\nNo veo ninguna iglesia.'
    assert observable_transcript(transcript)=='Veo 2 torres.\nNo veo ninguna iglesia.'
