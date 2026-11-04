import importlib.util
import json
import unittest

if importlib.util.find_spec('xgrammar') is None:
    raise unittest.SkipTest('xgrammar no instalado')

import torch
import xgrammar as xgr

from src.tfg_phase0.i20_assisted_annotation import annotation_draft_schema
from src.tfg_phase0.xgrammar_guidance import EXPECTED_QWEN3_VL_EOS_TOKEN_IDS,EXPECTED_QWEN3_VL_TEXT_VOCAB_SIZE,build_transformers_logits_processor,build_xgrammar_profile,compile_json_schema,resolve_text_vocab_size


MODEL='/home/dataai/models/hf/Qwen3-VL-8B-Instruct-0c351dd01ed8'
VOCAB=151936
EOS=(151643,151645)


def bit_allowed(mask,token_id):return bool((int(mask[0,token_id//32]) >> (token_id%32)) & 1)


class XGrammarGuidanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import transformers.tokenization_utils as tokenization_utils
        if not hasattr(tokenization_utils,'PreTrainedTokenizerBase'):
            from transformers import PreTrainedTokenizerBase
            tokenization_utils.PreTrainedTokenizerBase=PreTrainedTokenizerBase
        from transformers import AutoConfig,AutoTokenizer
        cls.config=AutoConfig.from_pretrained(MODEL,local_files_only=True)
        cls.tokenizer=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
        cls.resolved_vocab=resolve_text_vocab_size(cls.config,expected=VOCAB)
        cls.profile=build_xgrammar_profile(tokenizer=cls.tokenizer,vocab_size=cls.resolved_vocab,stop_token_ids=EOS)
        cls.compiled=compile_json_schema(cls.profile,annotation_draft_schema())

    def test_real_qwen_config_resolves_text_vocab_without_weights(self):
        self.assertEqual(self.resolved_vocab,151936);self.assertEqual(self.config.text_config.vocab_size,151936);self.assertEqual(EXPECTED_QWEN3_VL_TEXT_VOCAB_SIZE,151936);self.assertEqual(EXPECTED_QWEN3_VL_EOS_TOKEN_IDS,(151645,151643));self.assertEqual(self.profile.vocab_size,151936);self.assertEqual(self.profile.stop_token_ids,(151643,151645))

    def test_vocab_resolution_rejects_missing_invalid_and_mismatch(self):
        class Object:pass
        with self.assertRaisesRegex(ValueError,'sin text_config'):resolve_text_vocab_size(Object())
        outer=Object();outer.text_config=Object()
        with self.assertRaisesRegex(ValueError,'sin vocab_size'):resolve_text_vocab_size(outer)
        for value in (None,True,0,-1,'151936'):
            outer.text_config.vocab_size=value
            with self.subTest(value=value),self.assertRaises(ValueError):resolve_text_vocab_size(outer)
        outer.text_config.vocab_size=151935
        with self.assertRaisesRegex(ValueError,'incompatible'):resolve_text_vocab_size(outer,expected=151936)
        outer.text_config.vocab_size=151936
        with self.assertRaisesRegex(ValueError,'esperado inválido'):resolve_text_vocab_size(outer,expected=0)

    def test_unicode_controls_and_eos_are_safe(self):
        matcher=xgr.GrammarMatcher(self.compiled);mask=xgr.allocate_token_bitmask(1,VOCAB)
        prefix='{"description_es":"Una fotografía  ';ids=self.tokenizer.encode(prefix,add_special_tokens=False)
        for token_id in ids:self.assertTrue(matcher.accept_token(token_id))
        matcher.fill_next_token_bitmask(mask)
        self.assertFalse(bit_allowed(mask,5959))
        for eos in EOS:self.assertFalse(bit_allowed(mask,eos))

    def test_valid_nested_annotation_and_both_eos(self):
        description='Se observa una calle urbana con árboles.';text='una calle urbana';start=description.index(text)
        document={'description_es':description,'claims':[{'kind':'scene_structure','text_es':text,'span':{'start':start,'end':start+len(text)},'observability':'direct','certainty':'certain','requires_ocr':False,'requires_orientation':False,'orientation_frame':'unknown','limitations':[]}],'visible_text':[],'visual_uncertainty':{'overall_status':'adequate','limitations':[],'notes_es':None},'orientation':{'status':'unknown','bearing_degrees':None,'uncertainty_degrees':None,'meaning':'unknown','source':'not_available','evidence_ids':[],'cardinal_conversion_allowed':False},'human_review_required':True}
        raw=json.dumps(document,ensure_ascii=False,separators=(',',':'));matcher=xgr.GrammarMatcher(self.compiled);mask=xgr.allocate_token_bitmask(1,VOCAB)
        for token_id in self.tokenizer.encode(raw,add_special_tokens=False):self.assertTrue(matcher.accept_token(token_id))
        self.assertTrue(matcher.is_completed());matcher.fill_next_token_bitmask(mask)
        for eos in EOS:self.assertTrue(bit_allowed(mask,eos))
        self.assertTrue(matcher.accept_token(151645));self.assertTrue(matcher.is_terminated())

    def test_incomplete_required_fields_cannot_end(self):
        matcher=xgr.GrammarMatcher(self.compiled);mask=xgr.allocate_token_bitmask(1,VOCAB)
        for token_id in self.tokenizer.encode('{"description_es":"Texto suficientemente largo"}',add_special_tokens=False):
            if not matcher.accept_token(token_id):break
        self.assertFalse(matcher.is_completed());matcher.fill_next_token_bitmask(mask)
        for eos in EOS:self.assertFalse(bit_allowed(mask,eos))

    def test_hf_processor_masks_invalid_control_token(self):
        processor=build_transformers_logits_processor(self.compiled);prompt=torch.tensor([[42]],dtype=torch.long);scores=torch.zeros((1,VOCAB));processor(prompt,scores)
        prefix=self.tokenizer.encode('{"description_es":"Una fotografía  ',add_special_tokens=False);current=prompt
        for token_id in prefix:
            current=torch.cat([current,torch.tensor([[token_id]])],dim=1);scores=torch.zeros((1,VOCAB));processor(current,scores)
        self.assertTrue(torch.isneginf(scores[0,5959]));self.assertTrue(torch.isneginf(scores[0,151645]))


if __name__=='__main__':unittest.main()
