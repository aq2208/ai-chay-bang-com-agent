# AgentBase Custom Agent image for the Zalopay Issue Analytics Agent.
# Build for the platform (amd64) on Apple Silicon:
#   docker build --platform linux/amd64 -t vcr.vngcloud.vn/<repo>/<name>:<tag> .
#
# Python 3.11 (>=3.10 required by the SDK; 3.11 has the widest wheel coverage for
# torch / chromadb / sentence-transformers). Models and the KB index are baked in at
# build time so the runtime never downloads from HuggingFace on first request.
#
# Layer order is deliberate — least-changing layers first so GHA cache hits are
# maximised. Typical rebuild times:
#   Cold (first ever):          ~25 min  (downloads torch + models)
#   Requirements unchanged:     ~2-3 min (all expensive layers from GHA cache)
#   Only app code changed:      ~1-2 min (only COPY + index.py re-run)

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.hf_cache \
    TOKENIZERS_PARALLELISM=false

ARG HF_TOKEN
ENV HF_TOKEN=$HF_TOKEN

WORKDIR /app

# ── Layer 1: system build tools (changes almost never) ───────────────────────
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── Layer 2: pip deps (re-runs only when requirements.txt changes) ────────────
# pip cache mount speeds up re-runs when this layer IS invalidated.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt

# ── Layer 3: ML models (re-runs only when Layer 2 changes) ───────────────────
# Copy a pre-downloaded HF cache from the local host if present (local builds).
# The glob [e] makes this a no-op when the directory does not exist (CI).
COPY .hf_cach[e] /app/.hf_cache/

# Retry up to 3 times with backoff to handle transient HuggingFace network errors.
RUN for attempt in 1 2 3; do \
        python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')" && break; \
        echo "MiniLM download attempt $attempt failed — retrying in 20s..."; sleep 20; \
        [ $attempt -eq 3 ] && exit 1; \
    done \
    && for attempt in 1 2 3; do \
        python -c "from transformers import pipeline; pipeline('text-classification', model='wonrax/phobert-base-vietnamese-sentiment')" && break; \
        echo "PhoBERT download attempt $attempt failed — retrying in 20s..."; sleep 20; \
        [ $attempt -eq 3 ] && exit 1; \
    done

# ── Layer 4: app code (changes every commit) ──────────────────────────────────
COPY . .

# ── Layer 5: ChromaDB index (re-runs when knowledge_base/docs change) ─────────
RUN python knowledge_base/index.py

EXPOSE 8080
CMD ["python", "main.py"]
