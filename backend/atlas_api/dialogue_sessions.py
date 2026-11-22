"""Sesiones DialogueVPR persistentes; la inferencia se delega a un ejecutor explícito."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Protocol
import uuid


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, document: Mapping[str, Any]) -> None:
    payload = canonical(document) + b"\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


class DialogueExecutor(Protocol):
    def start(self, *, query_id: str, description: str, session_root: Path) -> Mapping[str, Any]: ...
    def answer(self, *, state: Mapping[str, Any], answer: str, answer_kind: str, session_root: Path) -> Mapping[str, Any]: ...


class DialogueUnavailable(RuntimeError): pass
class DialogueConflict(ValueError): pass


class DialogueSessionService:
    def __init__(self, *, cohort_path: Path | None, session_root: Path | None, image_root: Path | None, executor: DialogueExecutor | None, completed_query_ids: tuple[str, ...] = ("H26",), authorization_path: Path | None = None):
        self.session_root = session_root
        self.image_root = image_root
        self.executor = executor
        self.authorization_path = authorization_path
        self.completed = set(completed_query_ids)
        self.queries: dict[str, dict[str, Any]] = {}
        if cohort_path is not None and cohort_path.is_file():
            cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
            if cohort.get("contract_version") != "dialogue-development-cohort-v1": raise ValueError("cohorte DialogueVPR incompatible")
            self.cohort_id = cohort["cohort_id"]
            self.cohort_sha256 = sha256_file(cohort_path)
            self.queries = {row["query_id"]: row for row in cohort["queries"]}
        else:
            self.cohort_id = None
            self.cohort_sha256 = None
        if self.session_root is not None: self.session_root.mkdir(parents=True, exist_ok=True)

    @property
    def available(self) -> bool:
        return bool(self.queries and self.session_root and self.image_root and self.executor)

    def catalogue(self) -> dict[str, Any]:
        return {"schema_version":"1.0","contract_version":"atlas-dialogue-catalogue-v1","cohort_id":self.cohort_id,"available":self.available,"queries":[{"query_id":qid,"description_sha256":row["description_sha256"],"image_available":self.image_path(qid, required=False) is not None,"completed":qid in self.completed} for qid,row in self.queries.items()]}

    def image_path(self, query_id: str, *, required: bool = True) -> Path | None:
        row = self.queries.get(query_id)
        if row is None or self.image_root is None:
            if required: raise DialogueConflict("consulta o raíz de imágenes ausente")
            return None
        path = (self.image_root / Path(row["reference_image"]["logical_path"]).name).resolve()
        if self.image_root.resolve() not in path.parents or not path.is_file() or sha256_file(path) != row["reference_image"]["sha256"]:
            if required: raise DialogueConflict("imagen original ausente o hash divergente")
            return None
        return path

    def _session_path(self, session_id: str) -> Path:
        if not re.fullmatch(r"dialogue-[0-9a-f-]{36}", session_id) or self.session_root is None: raise DialogueConflict("session_id inválido")
        return self.session_root / session_id / "session.json"

    def _persist(self, document: dict[str, Any]) -> dict[str, Any]:
        document["updated_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        payload = {key:value for key,value in document.items() if key != "session_sha256"}
        document["session_sha256"] = sha256_bytes(canonical(payload))
        root = self._session_path(document["session_id"]).parent; root.mkdir(parents=True, exist_ok=True)
        atomic_write(root / "session.json", document)
        return document

    def start(self, *, mode: str, query_id: str, description: str) -> dict[str, Any]:
        if self.executor is None: raise DialogueUnavailable("runtime DialogueVPR no configurado")
        if mode == "official":
            row = self.queries.get(query_id)
            if row is None: raise DialogueConflict("HXX no pertenece a la cohorte")
            if query_id in self.completed: raise DialogueConflict("HXX ya está completado y congelado")
            if hashlib.sha256(description.encode()).hexdigest() != row["description_sha256"] or description != row["description_es"]: raise DialogueConflict("la descripción no coincide exactamente con la original congelada")
            image = self.image_path(query_id)
            image_record = {"sha256":sha256_file(image),"filename":image.name}
        else:
            if not query_id.startswith("X-"): raise DialogueConflict("las consultas exploratorias deben usar prefijo X-")
            image_record = None
        session_id = f"dialogue-{uuid.uuid4()}"; root = self._session_path(session_id).parent
        authorization = self._authorization(query_id=query_id, session_id=session_id)
        document = {"schema_version":"1.0","contract_version":"atlas-dialogue-session-v1","session_id":session_id,"mode":mode,"cohort_id":self.cohort_id if mode=="official" else None,"query_id":query_id,"description_es":description,"description_sha256":hashlib.sha256(description.encode()).hexdigest(),"image":image_record,"authorization":authorization,"status":"running","stop_reason":None,"state":{"status":"running","turns":[],"rounds":[],"claims":[],"answers":[]},"answers":[],"created_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        self._persist(document)
        try:
            state = dict(self.executor.start(query_id=query_id, description=description, session_root=root))
        except Exception as error:
            document["status"]="failed"; document["stop_reason"]="runtime_error_no_retry"; document["failure"]={"stage":"start","error_type":type(error).__name__}; self._persist(document)
            raise
        document["state"]=state; document["status"]=state["status"]; document["stop_reason"]=state.get("stop_reason")
        return self._persist(document)

    def _authorization(self, *, query_id: str, session_id: str) -> dict[str, Any]:
        if self.authorization_path is None or not self.authorization_path.is_file(): raise DialogueUnavailable("autorización de sesión DialogueVPR ausente")
        document=json.loads(self.authorization_path.read_text(encoding="utf-8"))
        required={"contract_version":"atlas-dialogue-session-authorization-v1","status":"OPERATOR_AUTHORIZED","approved":True,"query_id":query_id,"maximum_questions":3,"maximum_qwen_loads":3,"maximum_qwen_calls":3,"maximum_ct2l_loads":3,"maximum_ct2l_calls":3,"automatic_retries":0,"memory_policy":"stable-swap-v2","network_permitted":False,"ground_truth_permitted":False,"references_permitted":False,"vlm_permitted":False,"h38_h61_permitted":False}
        if any(document.get(key)!=value for key,value in required.items()): raise DialogueUnavailable("autorización de sesión incompatible")
        query=self.queries.get(query_id);identity=getattr(self.executor,'identity',{})
        expected={"cohort_sha256":self.cohort_sha256,"description_sha256":query.get('description_sha256') if query else None,"reference_image_sha256":query.get('reference_image',{}).get('sha256') if query else None,**identity}
        if any(document.get(key)!=value for key,value in expected.items()): raise DialogueUnavailable("hashes de autorización de sesión divergentes")
        if self.session_root is not None:
            for path in self.session_root.glob('dialogue-*/session.json'):
                try: used=json.loads(path.read_text()).get('authorization',{}).get('authorization_id')
                except (OSError,json.JSONDecodeError): continue
                if used==document['authorization_id']: raise DialogueUnavailable("autorización de sesión ya consumida")
        return {"authorization_id":document["authorization_id"],"authorization_sha256":sha256_file(self.authorization_path),"session_id":session_id,"consumed":True,"reusable_for_other_session":False}

    def load(self, session_id: str) -> dict[str, Any]:
        path = self._session_path(session_id)
        if not path.is_file(): raise DialogueConflict("sesión no encontrada")
        return json.loads(path.read_text(encoding="utf-8"))

    def answer(self, *, session_id: str, answer: str, answer_kind: str) -> dict[str, Any]:
        if self.executor is None: raise DialogueUnavailable("runtime DialogueVPR no configurado")
        document = self.load(session_id)
        if document["status"] != "awaiting_answer": raise DialogueConflict("la sesión no espera respuesta")
        answer_record={"turn_index":len(document["answers"])+1,"literal":answer,"sha256":hashlib.sha256(answer.encode()).hexdigest(),"answer_kind":answer_kind,"human_attested":True,"external_context_used":False}
        document["answers"].append(answer_record); document["status"]="running"; self._persist(document)
        try:
            state = dict(self.executor.answer(state=document["state"], answer=answer, answer_kind=answer_kind, session_root=self._session_path(session_id).parent))
        except Exception as error:
            document["status"]="failed"; document["stop_reason"]="runtime_error_no_retry"; document["failure"]={"stage":"answer","turn_index":answer_record["turn_index"],"error_type":type(error).__name__}; self._persist(document)
            raise
        document["state"] = state; document["status"] = state["status"]; document["stop_reason"] = state.get("stop_reason")
        return self._persist(document)

    def public(self, document: Mapping[str, Any]) -> dict[str, Any]:
        state = document["state"]; turns = state.get("turns", []); current = turns[-1] if document["status"] == "awaiting_answer" and turns else None
        return {"schema_version":"1.0","contract_version":"atlas-dialogue-session-public-v1","session_id":document["session_id"],"mode":document["mode"],"query_id":document["query_id"],"description_es":document["description_es"],"description_sha256":document["description_sha256"],"image_url":f"/api/v1/dialogue/queries/{document['query_id']}/image" if document.get("image") else None,"status":document["status"],"stop_reason":document.get("stop_reason"),"turn_count":len(turns),"answer_count":len(document["answers"]),"current_question":None if current is None else {"turn_index":current["index"],"question":current["question"]["question"],"question_sha256":current["question"]["question_sha256"],"intent_family":current["question"]["feature"]},"session_sha256":document["session_sha256"]}
