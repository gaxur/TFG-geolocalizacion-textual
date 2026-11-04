"""Adapter local Qwen3-VL para calidad técnica; carga diferida y sin red."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .visual_quality_gate import parse_quality_decision, quality_prompt, quality_schema


class LocalQwenVisualQualityVerifier:
    def __init__(self, *, model_path: Path, metadata: Mapping[str,Any]):
        import torch
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
        import transformers.tokenization_utils as tokenization_utils
        if not hasattr(tokenization_utils,"PreTrainedTokenizerBase"):
            from transformers import PreTrainedTokenizerBase
            tokenization_utils.PreTrainedTokenizerBase=PreTrainedTokenizerBase
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
        self._torch=torch;self._metadata=dict(metadata);self._processor=AutoProcessor.from_pretrained(model_path,local_files_only=True);self._model=Qwen3VLForConditionalGeneration.from_pretrained(model_path,local_files_only=True,dtype=torch.bfloat16,device_map="cuda",attn_implementation=metadata.get("attention","sdpa"));self._model.eval();self._prefix=build_transformers_prefix_allowed_tokens_fn(self._processor.tokenizer,JsonSchemaParser(quality_schema()))

    @property
    def metadata(self)->Mapping[str,Any]:return self._metadata

    def evaluate(self, *, image_path: Path)->Mapping[str,Any]:
        from PIL import Image
        image=Image.open(image_path).convert("RGB");inputs=self._processor.apply_chat_template([{"role":"user","content":[{"type":"image","image":image},{"type":"text","text":quality_prompt()}]}],tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors="pt").to(self._model.device)
        generation=self._metadata.get("generation",{"do_sample":False,"max_new_tokens":48,"batch_size":1})
        with self._torch.inference_mode():generated=self._model.generate(**inputs,max_new_tokens=generation["max_new_tokens"],do_sample=False,prefix_allowed_tokens_fn=self._prefix)
        raw=self._processor.batch_decode(generated[:,inputs.input_ids.shape[1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)[0]
        return parse_quality_decision(raw)

    def close(self)->None:
        model=self._model;self._model=None;del model;self._torch.cuda.empty_cache()
