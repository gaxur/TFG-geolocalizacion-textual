from pathlib import Path


path = Path("/usr/local/lib/python3.12/dist-packages/lmformatenforcer/integrations/transformers.py")
source = path.read_text(encoding="utf-8")
old = "from transformers.tokenization_utils import PreTrainedTokenizerBase"
new = "from transformers import PreTrainedTokenizerBase"
if source.count(old) != 1:
    raise RuntimeError("LMFE integration source does not match the verified 0.11.3 layout")
path.write_text(source.replace(old, new), encoding="utf-8")
