FROM crosstext2loc-gb10:f511

LABEL org.opencontainers.image.title="Qwen3-VL dialogue worker runtime" \
      org.opencontainers.image.base.name="crosstext2loc-gb10:f511" \
      es.tfg.dialogue-worker.base-image-id="sha256:0775ff6757f13f28c9950eff2d2ee6a2bf9f8f6bb465e2946453dce8f1caff72" \
      es.tfg.dialogue-worker.dependencies="lm-format-enforcer==0.11.3,interegular==0.3.3" \
      es.tfg.dialogue-worker.compatibility="LMFE PreTrainedTokenizerBase public import for Transformers 5.9.0"

COPY requirements.txt /tmp/qwen3-vl-dialogue-worker-requirements.txt
COPY patch_lmfe_transformers.py /tmp/patch_lmfe_transformers.py

RUN python -m pip install --no-cache-dir --no-deps --require-hashes \
        -r /tmp/qwen3-vl-dialogue-worker-requirements.txt && \
    python /tmp/patch_lmfe_transformers.py && \
    python -m pip check
