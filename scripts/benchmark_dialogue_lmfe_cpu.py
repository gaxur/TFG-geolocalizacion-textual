#!/usr/bin/env python3
"""Benchmark reproducible del callback LMFE de diálogo, sin pesos."""
import argparse,json,statistics,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.fail_closed_lmfe import FailClosedGuidanceError,build_fail_closed_transformers_prefix,replay_decoded_prefix
from src.tfg_phase0.visual_reranking import compact_atomic_verdict_schema

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tokenizer',type=Path,required=True);parser.add_argument('--output',type=Path);args=parser.parse_args()
    import torch
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(args.tokenizer,local_files_only=True);schema=compact_atomic_verdict_schema();optimized=build_fail_closed_transformers_prefix(tokenizer=tokenizer,schema=schema,eos_token_ids=[tokenizer.eos_token_id])
    class Legacy:
        def __init__(self,current):self.current=current;self.prompt_lengths={};self.decode_calls=0;self.verified_candidates=0;self.candidates_examined=0
        def decode(self,ids):self.decode_calls+=1;return tokenizer.decode(ids,skip_special_tokens=True,clean_up_tokenization_spaces=False)
        def replay(self,ids):return replay_decoded_prefix(self.current.parser_factory,self.decode(ids))
        def __call__(self,batch,sent):
            sequence=sent.tolist();self.prompt_lengths.setdefault(batch,len(sequence));generated=sequence[self.prompt_lengths[batch]:];state=self.replay(generated);allowed=[];candidates=self.current.lmfe_prefix(batch,sent);self.candidates_examined+=len(candidates)
            for token_id in candidates:
                token_id=int(token_id)
                if token_id in self.current.eos_token_ids:
                    if state.can_end():allowed.append(token_id)
                elif token_id in self.current.verified_token_ids:
                    self.verified_candidates+=1
                    try:self.replay([*generated,token_id])
                    except FailClosedGuidanceError:continue
                    allowed.append(token_id)
                else:allowed.append(token_id)
            if not allowed:raise FailClosedGuidanceError('ningún token mantiene válida la decodificación final')
            return allowed
    legacy_base=build_fail_closed_transformers_prefix(tokenizer=tokenizer,schema=schema,eos_token_ids=[tokenizer.eos_token_id]);legacy=Legacy(legacy_base);raw=json.dumps({'verdict':'supported','observed_evidence':'three colored geometric shapes are visible','ocr_text':'FORMAS Y COLORES','limitations':['none']},separators=(',',':'));tokens=tokenizer.encode(raw,add_special_tokens=False)
    def run(wrapper):
        sequence=tokenizer.encode('prompt',add_special_tokens=False);latencies=[]
        for token_id in tokens:
            started=time.perf_counter();allowed=wrapper(0,torch.tensor(sequence));latencies.append((time.perf_counter()-started)*1000)
            if token_id not in allowed or tokenizer.eos_token_id in allowed:raise RuntimeError('garantía fail-closed divergente')
            sequence.append(token_id)
        if tokenizer.eos_token_id not in wrapper(0,torch.tensor(sequence)):raise RuntimeError('EOS final rechazado')
        return {'median_ms':statistics.median(latencies),'maximum_ms':max(latencies),'total_ms':sum(latencies)}
    before=run(legacy);after=run(optimized);report={'schema_version':'1.0','contract_version':'dialogue-lmfe-cpu-benchmark-v1','tokenizer':str(args.tokenizer),'document_tokens':len(tokens),'before':{'latency':before,'decode_calls':legacy.decode_calls,'candidates_examined':legacy.candidates_examined,'verified_candidates':legacy.verified_candidates},'after':{'latency':after,**optimized.metrics_snapshot()},'speedup_total':before['total_ms']/after['total_ms'],'decode_call_reduction_fraction':1-optimized.metrics_snapshot()['decode_calls']/legacy.decode_calls,'valid_document_accepted':True,'premature_eos_blocked':True,'complete_eos_allowed':True}
    payload=json.dumps(report,sort_keys=True,indent=2);print(payload)
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(payload+'\n')
    return 0
if __name__=='__main__':raise SystemExit(main())
