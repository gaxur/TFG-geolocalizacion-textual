FROM nvcr.io/nvidia/pytorch@sha256:8014e4ffc674ae9cc9aecad04b64b29c3d311ed738e54ac3042d2d45690d19e9

ARG OPENAI_CLIP_COMMIT=dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1

COPY cross-text2loc-requirements.txt /tmp/cross-text2loc-requirements.txt

RUN python -m pip install --no-cache-dir --constraint /etc/pip/constraint.txt \
        -r /tmp/cross-text2loc-requirements.txt && \
    python -m pip install --no-cache-dir "setuptools==80.10.2" && \
    python -m pip install --no-cache-dir --no-build-isolation \
        "clip @ git+https://github.com/openai/CLIP.git@${OPENAI_CLIP_COMMIT}"

WORKDIR /workspace/CVG-Text
