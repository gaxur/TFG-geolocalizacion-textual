#!/usr/bin/env python3
"""Benchmark CPU reproducible de restricciones JSON, sin cargar pesos."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import resource
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from src.tfg_phase0.i20_assisted_annotation import annotation_draft_schema


def summary(values):
    ordered=sorted(values)
    percentile=lambda p:ordered[min(len(ordered)-1,math.ceil(p*len(ordered))-1)]
    return {'count':len(values),'median_ms':statistics.median(values)*1000,'p95_ms':percentile(.95)*1000,'minimum_ms':ordered[0]*1000,'maximum_ms':ordered[-1]*1000}


def timed(call,repetitions=7):
    values=[];result=None
    for _ in range(repetitions):
        start=time.perf_counter();result=call();values.append(time.perf_counter()-start)
    return result,summary(values)


def sample_document():
    description='Se observa una calle urbana con edificios y árboles.';text='una calle urbana';start=description.index(text)
    return {'description_es':description,'claims':[{'kind':'scene_structure','text_es':text,'span':{'start':start,'end':start+len(text)},'observability':'direct','certainty':'certain','requires_ocr':False,'requires_orientation':False,'orientation_frame':'unknown','limitations':[]}],'visible_text':[],'visual_uncertainty':{'overall_status':'adequate','limitations':[],'notes_es':None},'orientation':{'status':'unknown','bearing_degrees':None,'uncertainty_degrees':None,'meaning':'unknown','source':'not_available','evidence_ids':[],'cardinal_conversion_allowed':False},'human_review_required':True}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tokenizer',type=Path,required=True);parser.add_argument('--output',type=Path);args=parser.parse_args()
    import torch
    import transformers.tokenization_utils as tokenization_utils
    if not hasattr(tokenization_utils,'PreTrainedTokenizerBase'):
        from transformers import PreTrainedTokenizerBase
        tokenization_utils.PreTrainedTokenizerBase=PreTrainedTokenizerBase
    from transformers import AutoTokenizer
    from lmformatenforcer import JsonSchemaParser
    from lmformatenforcer.characterlevelparser import CharacterLevelParserConfig
    from lmformatenforcer.integrations.transformers import build_token_enforcer_tokenizer_data,build_transformers_prefix_allowed_tokens_fn
    from src.tfg_phase0.fail_closed_lmfe import build_fail_closed_transformers_prefix
    import xgrammar as xgr

    schema=annotation_draft_schema();schema_text=json.dumps(schema,ensure_ascii=False,sort_keys=True,separators=(',',':'));document=json.dumps(sample_document(),ensure_ascii=False,separators=(',',':'))
    started=time.perf_counter();tokenizer=AutoTokenizer.from_pretrained(args.tokenizer,local_files_only=True);tokenizer_load=time.perf_counter()-started
    token_ids=tokenizer.encode(document,add_special_tokens=False);vocab_size=151936;eos_ids=[151645,151643]

    started=time.perf_counter();tokenizer_data=build_token_enforcer_tokenizer_data(tokenizer);lmfe_tokenizer_setup=time.perf_counter()-started
    correct_config=lambda:CharacterLevelParserConfig(alphabet=tokenizer_data.tokenizer_alphabet)
    started=time.perf_counter();lmfe_original=build_transformers_prefix_allowed_tokens_fn(tokenizer_data,JsonSchemaParser(schema,config=correct_config()));lmfe_compile=time.perf_counter()-started
    started=time.perf_counter();lmfe_v7=build_fail_closed_transformers_prefix(tokenizer=tokenizer,schema=schema,eos_token_ids=eos_ids);lmfe_v7_setup=time.perf_counter()-started

    started=time.perf_counter();tokenizer_info=xgr.TokenizerInfo.from_huggingface(tokenizer,vocab_size=vocab_size,stop_token_ids=eos_ids);xgr_tokenizer_setup=time.perf_counter()-started
    compiler=xgr.GrammarCompiler(tokenizer_info,max_threads=8,cache_enabled=True);started=time.perf_counter();compiled=compiler.compile_json_schema(schema,strict_mode=True);xgr_compile=time.perf_counter()-started

    class Tensor:
        def __init__(self,values):self.values=values
        def tolist(self):return list(self.values)
    prompt=[42];original_sequence=list(prompt);v7_sequence=list(prompt);lmfe_original(0,Tensor(original_sequence));lmfe_v7(0,Tensor(v7_sequence))
    lmfe_steps=[];v7_steps=[];states=[];v7_stopped=None;lmfe_rejection=None;v7_rejection=None
    for index,token_id in enumerate(token_ids):
        label='structure'
        decoded=tokenizer.decode(token_ids[:index+1],skip_special_tokens=True,clean_up_tokenization_spaces=False)
        if '"description_es":"' in decoded and '"claims"' not in decoded:label='free_text'
        elif '"claims"' in decoded and '"orientation"' not in decoded:label='claims_nested'
        elif '"orientation"' in decoded:label='orientation_or_end'
        if lmfe_rejection is None:
            start=time.perf_counter();original_allowed=lmfe_original(0,Tensor(original_sequence));original_elapsed=time.perf_counter()-start;lmfe_steps.append(original_elapsed)
            if token_id not in original_allowed:lmfe_rejection={'index':index,'token_id':token_id,'token_text':tokenizer.decode([token_id]),'prefix':decoded}
            else:original_sequence.append(token_id)
        if v7_rejection is None and v7_stopped is None:
            start=time.perf_counter();v7_allowed=lmfe_v7(0,Tensor(v7_sequence));v7_elapsed=time.perf_counter()-start;v7_steps.append(v7_elapsed);states.append(label)
            if token_id not in v7_allowed:v7_rejection={'index':index,'token_id':token_id,'token_text':tokenizer.decode([token_id]),'prefix':decoded}
            else:v7_sequence.append(token_id)
            if sum(v7_steps)>20:v7_stopped={'after_tokens':index+1,'reason':'benchmark_cpu_budget_20_seconds'}

    matcher=xgr.GrammarMatcher(compiled);bitmask=xgr.allocate_token_bitmask(1,vocab_size);xgr_fill=[];xgr_accept=[];xgr_apply=[];xgr_states=[]
    scores=torch.zeros((1,vocab_size),dtype=torch.float32)
    for token_id in token_ids:
        accepted_prefix=tokenizer.decode(token_ids[:len(xgr_states)+1],skip_special_tokens=True,clean_up_tokenization_spaces=False);label='structure'
        if '"description_es":"' in accepted_prefix and '"claims"' not in accepted_prefix:label='free_text'
        elif '"claims"' in accepted_prefix and '"orientation"' not in accepted_prefix:label='claims_nested'
        elif '"orientation"' in accepted_prefix:label='orientation_or_end'
        xgr_states.append(label)
        start=time.perf_counter();matcher.fill_next_token_bitmask(bitmask);xgr_fill.append(time.perf_counter()-start)
        local_scores=scores.clone();start=time.perf_counter();xgr.apply_token_bitmask_inplace(local_scores,bitmask,vocab_size=vocab_size,backend='cpu');xgr_apply.append(time.perf_counter()-start)
        if not math.isfinite(float(local_scores[0,token_id])):raise RuntimeError('XGrammar enmascaró token válido')
        start=time.perf_counter();accepted=matcher.accept_token(token_id);xgr_accept.append(time.perf_counter()-start)
        if not accepted:raise RuntimeError('XGrammar rechazó token válido')
    matcher.fill_next_token_bitmask(bitmask);before_eos=matcher.is_completed();eos_accepted=matcher.accept_token(151645);after_eos=matcher.is_terminated()

    def grouped(values,labels):
        return {label:summary([value for value,current in zip(values,labels) if current==label]) for label in sorted(set(labels))}
    report={'schema_sha256':__import__('hashlib').sha256(schema_text.encode()).hexdigest(),'tokenizer':str(args.tokenizer),'vocab_size':vocab_size,'document_tokens':len(token_ids),'document_characters':len(document),'environment':{'python':sys.version.split()[0],'machine':__import__('platform').machine(),'lmfe':__import__('importlib.metadata').metadata.version('lm-format-enforcer'),'xgrammar':__import__('importlib.metadata').metadata.version('xgrammar'),'transformers':__import__('importlib.metadata').metadata.version('transformers')},'setup_seconds':{'tokenizer_load':tokenizer_load,'lmfe_tokenizer_data':lmfe_tokenizer_setup,'lmfe_parser_enforcer':lmfe_compile,'lmfe_v7_full_setup':lmfe_v7_setup,'xgrammar_tokenizer_info':xgr_tokenizer_setup,'xgrammar_compile':xgr_compile},'per_step':{'lmfe_original':summary(lmfe_steps),'lmfe_rejection':lmfe_rejection,'lmfe_v7':summary(v7_steps),'lmfe_v7_by_state':grouped(v7_steps,states),'lmfe_v7_rejection':v7_rejection,'lmfe_v7_stopped':v7_stopped,'xgrammar_fill_mask':summary(xgr_fill),'xgrammar_fill_by_state':grouped(xgr_fill,xgr_states),'xgrammar_apply_cpu_logits':summary(xgr_apply),'xgrammar_accept':summary(xgr_accept)},'xgrammar':{'compiled_memory_bytes':compiled.memory_size_bytes,'completed_before_eos':before_eos,'eos_accepted':eos_accepted,'terminated_after_eos':after_eos,'bitmask_shape':list(bitmask.shape)},'rss_peak_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'extrapolation_ms':{engine:{'512_tokens':metrics['median_ms']*512,'2048_tokens':metrics['median_ms']*2048} for engine,metrics in [('lmfe_original',summary(lmfe_steps)),('lmfe_v7',summary(v7_steps)),('xgrammar_matcher',summary([a+b for a,b in zip(xgr_fill,xgr_accept)])),('xgrammar_with_cpu_mask',summary([a+b+c for a,b,c in zip(xgr_fill,xgr_accept,xgr_apply)]))]}}
    payload=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2);print(payload)
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(payload+'\n')
    return 0

if __name__=='__main__':raise SystemExit(main())
