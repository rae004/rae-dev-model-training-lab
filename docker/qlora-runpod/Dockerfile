# QLoRA training image (ADR-026, M12). Built on command, pushed to
# ghcr.io/rae004/rae-dev-model-training-lab-qlora, run on RunPod.
#
# The pip installs below are the sanctioned exception to CLAUDE.md rule 1:
# training planes install torch in a container, never in the shared
# CPU-only lockfile (ADR-003). Versions pinned 2026-11-26 (latest stable
# at authoring); the M12 smoke run on a cheap pod validates the set
# before any A100 time is bought.
#
# cu128 base per ADR-026. llama.cpp is cloned at a pinned release for
# GGUF conversion: the convert script + llama-quantize binary live there
# (the ADR names llama-cpp-python for this role, but the converter ships
# with llama.cpp itself, not the Python binding — same intent, working
# implementation).

FROM nvidia/cuda:12.8.0-devel-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/workspace/hf

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv git ca-certificates \
        cmake build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Ubuntu 24.04 marks the system Python externally managed; the container
# still gets a venv so the image's Python surface is explicit.
RUN python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

RUN pip install torch --index-url https://download.pytorch.org/whl/cu128

RUN pip install \
        transformers==5.24.1 \
        peft==0.22.0 \
        trl==1.19.0 \
        bitsandbytes==0.50.2 \
        kernels==0.19.0 \
        accelerate==1.16.0 \
        datasets==5.2.0 \
        huggingface_hub==2.5.0

# llama.cpp for GGUF conversion: convert_hf_to_gguf.py + llama-quantize.
# CPU-only build — conversion is not a GPU job. The converter's
# requirements pin an older transformers/hub and silently downgraded the
# training stack when installed into the same venv (first local build),
# so they live in their own venv; train_qlora.py invokes the convert
# script with /opt/convert-venv/bin/python.
RUN git clone --depth 1 --branch v1.1.0 \
        https://github.com/ggml-org/llama.cpp /opt/llama.cpp \
    && cmake -S /opt/llama.cpp -B /opt/llama.cpp/build \
        -DGGML_CUDA=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
    && cmake --build /opt/llama.cpp/build --target llama-quantize -j"$(nproc)" \
    && python3 -m venv /opt/convert-venv \
    && /opt/convert-venv/bin/pip install --no-cache-dir \
        -r /opt/llama.cpp/requirements/requirements-convert_hf_to_gguf.txt

# Triton JIT-compiles a CUDA utils shim at runtime (TRL 1.19's fused
# kernels) and needs Python.h. Installed in its own late layer rather
# than the apt block above so fixing it didn't rebuild the 29GB of
# torch/HF layers.
RUN apt-get update && apt-get install -y --no-install-recommends python3-dev \
    && rm -rf /var/lib/apt/lists/*

# The repo at a specific SHA (ADR-026): config + entrypoint travel with
# the image, so a run is regenerable from the image tag alone.
ARG REPO_SHA
RUN test -n "$REPO_SHA" || (echo "build with --build-arg REPO_SHA=<sha>" && false)
RUN git clone https://github.com/rae004/rae-dev-model-training-lab /workspace/repo \
    && git -C /workspace/repo checkout --detach "$REPO_SHA"

WORKDIR /workspace/repo

# RUN_TAG, HF_TOKEN (and optionally MAX_PAIRS, MAX_EPOCHS for the smoke
# slice) come in as pod env/secrets. The entrypoint stops its own pod
# via RunPod's injected pod-scoped RUNPOD_API_KEY when done — RunPod
# restarts the container on any exit, so plain exit 0 would loop
# (ADR-026 assumed otherwise; same intent, working implementation).
CMD ["python", "docker/qlora-runpod/train_qlora.py", "--config", "configs/qlora_baseline.toml"]
