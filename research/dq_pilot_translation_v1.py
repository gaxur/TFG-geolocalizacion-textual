"""Contrato EN->ES fail-closed; no selecciona ni carga un traductor."""
from __future__ import annotations
import hashlib,re
from typing import Any,Mapping

class TranslationContractError(ValueError):pass
SPANISH_MARKERS=re.compile(r"[¿¡áéíóúñ]|\b(?:hay|ves|puedes|tiene|está|es|una|un|la|el)\b",re.I)
ENGLISH_MARKERS=re.compile(r"\b(?:is|are|does|do|can|what|which|the|there)\b",re.I)
def digest_text(value:str)->str:return hashlib.sha256(value.encode()).hexdigest()
def validate_translation(document:Mapping[str,Any],*,round_index:int,source_question:str,translator_identity:Mapping[str,Any])->dict[str,Any]:
 required={"schema_version","contract_version","status","round_index","source_language","target_language","source_question","source_question_sha256","translated_question","translated_question_sha256","translator","semantic_repair_performed","automatic_retries","fallback_used","network_used","validation"}
 allowed=required|{"step"}
 if not required<=set(document) or not set(document)<=allowed or document.get("schema_version")!="1.0" or document.get("contract_version")!="dq-pilot-translation-result-v1" or document.get("status")!="translated_pending_human_review" or ("step" in document and document["step"]!="spanish-translation"):raise TranslationContractError("contrato/status de traducción incompatible")
 if type(document.get("round_index")) is not int or document["round_index"]!=round_index or document.get("source_language")!="en" or document.get("target_language")!="es":raise TranslationContractError("ronda/idiomas de traducción incompatibles")
 if document.get("source_question")!=source_question or document.get("source_question_sha256")!=digest_text(source_question):raise TranslationContractError("pregunta fuente/hash divergente")
 translated=document.get("translated_question")
 if type(translated)is not str or not translated.strip() or translated==source_question or document.get("translated_question_sha256")!=digest_text(translated):raise TranslationContractError("traducción vacía, sin traducir o hash divergente")
 if document.get("translator")!=dict(translator_identity) or translator_identity.get("local") is not True or not translator_identity.get("translator_id") or not translator_identity.get("version") or not translator_identity.get("artifact_manifest_sha256"):raise TranslationContractError("identidad local del traductor no fijada")
 if document.get("semantic_repair_performed") is not False or document.get("automatic_retries")!=0 or document.get("fallback_used") is not False or document.get("network_used") is not False:raise TranslationContractError("reparación/retry/fallback/red prohibidos")
 validation=document.get("validation")
 if validation!={"structural":"passed","semantic":"pending_human_review","source_question_preserved":True,"human_review_required":True}:raise TranslationContractError("validación de traducción incompatible")
 if not translated.rstrip().endswith("?") or translated.count("?")!=1 or not SPANISH_MARKERS.search(translated) or ENGLISH_MARKERS.search(translated):raise TranslationContractError("idioma/interrogación de traducción no verificados")
 return dict(document)

class UnavailableSpanishTranslator:
 identity={"translator_id":None,"version":None,"artifact_manifest_sha256":None,"runtime":None,"status":"TRANSLATION_UNAVAILABLE","local":False,"candidate":"Helsinki-NLP/opus-mt-en-es"}
 def translate(self,*,round_index:int,question:str)->Mapping[str,Any]:raise TranslationContractError("TRANSLATION_UNAVAILABLE: checkpoint/revision/runtime/corpus EN-ES no validados")
