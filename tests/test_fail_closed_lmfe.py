import importlib.util
import json
import unittest
from pathlib import Path

if importlib.util.find_spec('lmformatenforcer') is None:
    raise unittest.SkipTest('lm-format-enforcer no instalado')

from lmformatenforcer import JsonSchemaParser
from lmformatenforcer.characterlevelparser import CharacterLevelParserConfig

from src.tfg_phase0.fail_closed_lmfe import FailClosedGuidanceError,FailClosedPrefixAllowedTokens,advance_json_string_field_state,build_fail_closed_transformers_prefix,enforce_json_string_field_limit,json_string_field_state,json_string_token_within_limit,replay_decoded_prefix
from src.tfg_phase0.i20_assisted_annotation import annotation_draft_schema


ROOT=Path(__file__).resolve().parents[1]
V6_RAW=ROOT/'results/generated/i01-i20-assisted-annotation-v6/diagnostics/attempts/annotation-I01/attempt-001/raw.json'


class Tensor:
    def __init__(self,values):self.values=values
    def tolist(self):return list(self.values)


class SyntheticTokenizer:
    def __init__(self,mapping):self.mapping=mapping
    def decode(self,ids,**kwargs):return ''.join(self.mapping.get(i,'') for i in ids)


class FailClosedLmfeTests(unittest.TestCase):
    def test_json_string_limit_counts_unicode_characters_and_escapes(self):
        for value,expected in (("a"*119,119),("á"*120,120),("\\u00e1"*120,120)):
            text='{"observed_evidence":"'+value+'"}';self.assertEqual(json_string_field_state(text,'observed_evidence')['count'],expected);enforce_json_string_field_limit(text,'observed_evidence',120)
        with self.assertRaises(FailClosedGuidanceError):enforce_json_string_field_limit('{"observed_evidence":"'+'á'*121+'"}','observed_evidence',120)

    def test_multichar_token_cannot_cross_string_limit(self):
        schema={'type':'object','additionalProperties':False,'required':['x'],'properties':{'x':{'type':'string','maxLength':3}}};tokenizer=SyntheticTokenizer({1:'{"x":"ab',2:'cd',3:'c',4:'"}',9:''});wrapper=FailClosedPrefixAllowedTokens(tokenizer=tokenizer,parser_factory=lambda:JsonSchemaParser(schema),lmfe_prefix=lambda batch,sent:[2,3,4,9],eos_token_ids=[9],token_texts={2:'cd',3:'c',4:'"}'},string_field_limits={'x':3});wrapper.prompt_lengths[0]=1
        allowed=wrapper(0,Tensor([100,1]));self.assertNotIn(2,allowed);self.assertIn(3,allowed);self.assertNotIn(9,allowed)

    def test_incremental_string_state_handles_escape_across_token_boundary(self):
        state={"count":119,"closed":False,"escape":False,"unicode_remaining":0};state=advance_json_string_field_state(state,'\\u00',120);self.assertEqual(state['unicode_remaining'],2);state=advance_json_string_field_state(state,'e1"',120);self.assertEqual(state['count'],120);self.assertTrue(state['closed'])
        self.assertTrue(json_string_token_within_limit({"count":119,"closed":False,"escape":False,"unicode_remaining":0},'á',120));self.assertFalse(json_string_token_within_limit({"count":120,"closed":False,"escape":False,"unicode_remaining":0},'ab',120))

    def test_character_parser_rejects_literal_lf_and_incomplete_eos(self):
        parser=JsonSchemaParser({'type':'object','required':['x'],'properties':{'x':{'type':'string'}}})
        for character in '{"x":"A':
            self.assertIn(character,parser.get_allowed_characters());parser=parser.add_character(character)
        self.assertNotIn('\n',parser.get_allowed_characters());self.assertFalse(parser.can_end())

    def test_v6_raw_is_preserved_but_cannot_replay(self):
        document=json.loads(V6_RAW.read_text());raw=document['raw_output']
        self.assertNotIn('token_ids',document['generation']);self.assertNotIn('generated_token_ids',document['generation'])
        self.assertTrue(document['generation']['terminated_by_eos']);self.assertFalse(document['generation']['reached_max_new_tokens'])
        with self.assertRaises(FailClosedGuidanceError):replay_decoded_prefix(lambda:JsonSchemaParser(annotation_draft_schema()),raw)

    def test_wrapper_blocks_multichar_control_token_and_premature_eos(self):
        tokenizer=SyntheticTokenizer({1:'{"x":"A',2:'\n\n',3:'"}',9:''})
        underlying=lambda batch,sent:[1] if len(sent.tolist())==1 else [2,3,9]
        wrapper=FailClosedPrefixAllowedTokens(tokenizer=tokenizer,parser_factory=lambda:JsonSchemaParser({'type':'object','required':['x'],'properties':{'x':{'type':'string'}}}),lmfe_prefix=underlying,eos_token_ids=[9],verified_token_ids=[2,3])
        allowed=wrapper(0,Tensor([100]));self.assertEqual(allowed,[1])
        allowed=wrapper(0,Tensor([100,1]));self.assertNotIn(2,allowed);self.assertNotIn(9,allowed);self.assertIn(3,allowed)

    def test_wrapper_allows_eos_only_after_complete_required_object(self):
        tokenizer=SyntheticTokenizer({1:'{"x":"ok"}',9:''});wrapper=FailClosedPrefixAllowedTokens(tokenizer=tokenizer,parser_factory=lambda:JsonSchemaParser({'type':'object','required':['x'],'properties':{'x':{'type':'string'}}}),lmfe_prefix=lambda batch,sent:[9],eos_token_ids=[9]);wrapper.prompt_lengths[0]=1
        self.assertEqual(wrapper(0,Tensor([100,1])),[9])

    def test_wrapper_rejects_existing_invalid_prefix_fail_closed(self):
        tokenizer=SyntheticTokenizer({1:'{"x":"bad\n',9:''});wrapper=FailClosedPrefixAllowedTokens(tokenizer=tokenizer,parser_factory=lambda:JsonSchemaParser({'type':'object','required':['x'],'properties':{'x':{'type':'string'}}}),lmfe_prefix=lambda batch,sent:[9],eos_token_ids=[9]);wrapper.prompt_lengths[0]=1
        with self.assertRaises(FailClosedGuidanceError):wrapper(0,Tensor([100,1]))

    def test_incremental_state_reuses_prefix_and_tracks_metrics(self):
        tokenizer=SyntheticTokenizer({1:'{"x":"',2:'á',3:'"}',9:''});config=CharacterLevelParserConfig();config.alphabet+='á';wrapper=FailClosedPrefixAllowedTokens(tokenizer=tokenizer,parser_factory=lambda:JsonSchemaParser({'type':'object','additionalProperties':False,'required':['x'],'properties':{'x':{'type':'string'}}},config=config),lmfe_prefix=lambda batch,sent:[1,2,3,9],eos_token_ids=[9],verified_token_ids=[2]);sequence=[100];wrapper(0,Tensor(sequence));sequence.append(1);wrapper(0,Tensor(sequence));sequence.append(2);wrapper(0,Tensor(sequence));sequence.append(3);allowed=wrapper(0,Tensor(sequence));metrics=wrapper.metrics_snapshot()
        self.assertIn(9,allowed);self.assertEqual(metrics['calls'],4);self.assertEqual(metrics['candidates_examined'],16);self.assertGreater(metrics['parser_characters'],0)

    def test_wrapper_rejects_unknown_field_and_no_candidates(self):
        schema={'type':'object','additionalProperties':False,'required':['x'],'properties':{'x':{'type':'string'}}}
        with self.assertRaises(FailClosedGuidanceError):replay_decoded_prefix(lambda:JsonSchemaParser(schema),'{"y":"bad"}')
        wrapper=FailClosedPrefixAllowedTokens(tokenizer=SyntheticTokenizer({}),parser_factory=lambda:JsonSchemaParser(schema),lmfe_prefix=lambda batch,sent:[],eos_token_ids=[9])
        with self.assertRaises(FailClosedGuidanceError):wrapper(0,Tensor([100]))

    def test_nested_arrays_booleans_and_required_fields_complete(self):
        schema={'type':'object','additionalProperties':False,'required':['ok','items'],'properties':{'ok':{'type':'boolean'},'items':{'type':'array','minItems':1,'items':{'type':'object','required':['x'],'properties':{'x':{'type':'null'}}}}}}
        parser=replay_decoded_prefix(lambda:JsonSchemaParser(schema),'{"ok":true,"items":[{"x":null}]}');self.assertTrue(parser.can_end())

    def test_real_qwen_tokenizer_blocks_v6_synthetic_retokenization(self):
        try:
            import torch
            import transformers.tokenization_utils as tokenization_utils
            if not hasattr(tokenization_utils,'PreTrainedTokenizerBase'):
                from transformers import PreTrainedTokenizerBase
                tokenization_utils.PreTrainedTokenizerBase=PreTrainedTokenizerBase
            from transformers import AutoTokenizer
        except ImportError:
            self.skipTest('integración Transformers no disponible')
        tokenizer=AutoTokenizer.from_pretrained('/home/dataai/models/hf/Qwen3-VL-8B-Instruct-0c351dd01ed8',local_files_only=True)
        raw=json.loads(V6_RAW.read_text())['raw_output'];ids=tokenizer.encode(raw,add_special_tokens=False)
        wrapper=build_fail_closed_transformers_prefix(tokenizer=tokenizer,schema=annotation_draft_schema(),eos_token_ids=[tokenizer.eos_token_id]);prompt=tokenizer.encode('prompt',add_special_tokens=False);sequence=list(prompt);wrapper(0,torch.tensor(sequence));blocked=None
        for index,token_id in enumerate(ids):
            allowed=wrapper(0,torch.tensor(sequence))
            self.assertNotIn(tokenizer.eos_token_id,allowed)
            if token_id not in allowed:
                blocked=(index,token_id,tokenizer.decode([token_id]));break
            sequence.append(token_id)
        self.assertEqual(blocked[1],5959);self.assertIn('\n',blocked[2])


if __name__=='__main__':unittest.main()
