"""Composición mínima del controlador iterativo con adapters reales inyectados."""
from __future__ import annotations
from pathlib import Path
from typing import Any,Mapping
from research.dq_pilot_iterative_controller_v1 import IterativeDialogueController,IterativeRunStore
from research.dq_pilot_real_adapters_v1 import DQPilotHostValidatorAdapter,MetadataOnlyMapillaryPanelAdapter,PreparedDQPilotQuestionerAdapter,RealCT2LRetrieverAdapter,RealTextInterpreterAdapter
from research.dq_pilot_translation_v1 import UnavailableSpanishTranslator

def build_iterative_pipeline(*,qwen_port,retrieval_port,query_id:str,visual_dataset_id:str,embedding_dataset_id:str,catalog:Mapping[str,Any],inventory:Mapping[str,Any],cache_root:Path,original_description:str,session_id:str,outcome_schema:Mapping[str,Any],execution_port=None,processor_expectation_resolver=None,translator=None,top_n:int=20):
 interpreter=RealTextInterpreterAdapter(qwen_port);retriever=RealCT2LRetrieverAdapter(retrieval_port,query_id=query_id,visual_dataset_id=visual_dataset_id,embedding_dataset_id=embedding_dataset_id);panel=MetadataOnlyMapillaryPanelAdapter(catalog=catalog,inventory=inventory,cache_root=cache_root,original_description=original_description,session_id=session_id);questioner=PreparedDQPilotQuestionerAdapter(cache_root=cache_root,execution_port=execution_port,processor_expectation_resolver=processor_expectation_resolver);validator=DQPilotHostValidatorAdapter(outcome_schema=outcome_schema);translator=translator or UnavailableSpanishTranslator();controller=IterativeDialogueController(interpreter=interpreter,retriever=retriever,panel=panel,questioner=questioner,validator=validator,translator=translator,top_n=top_n);identities={"interpreter":dict(interpreter.identity),"retriever":dict(retriever.identity),"panel":dict(panel.identity),"questioner":dict(questioner.identity),"validator":dict(validator.identity),"translator":dict(translator.identity)};return controller,identities

def prepare_iterative_run(root:Path,*,controller:IterativeDialogueController,identities:Mapping[str,Any],session_id:str,query_id:str,original_description:str,top_n:int=20):
 return IterativeRunStore.prepare(root,session_id=session_id,query_id=query_id,original_description=original_description,top_n=top_n,identities=identities)
