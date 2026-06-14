# AgentBase Custom Agent image for the Zalopay Issue Analytics Agent.
# Build for the platform (amd64) on Apple Silicon:
#   docker build --platform linux/amd64 -t vcr.vngcloud.vn/<repo>/<name>:<tag> .
#
# Python 3.11 (>=3.10 required by the SDK; 3.11 has the widest wheel coverage for
# torch / chromadb / sentence-transformers). Models and the KB index are baked in at
# build time so the runtime never downloads from HuggingFace on first request.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.hf_cache \
    TOKENIZERS_PARALLELISM=false

ARG HF_TOKEN
ENV HF_TOKEN=$HF_TOKEN

WORKDIR /app

# Build tools for any deps without prebuilt wheels (e.g. hnswlib used by chromadb).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first (smaller, no CUDA), then the rest.
COPY requirements.txt .

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Copy the pre-downloaded Hugging Face cache from local host
COPY .hf_cache /app/.hf_cache

# Bake the ML models into the image (PhoBERT sentiment + MiniLM embeddings).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')" \
    && python -c "from transformers import pipeline; pipeline('text-classification', model='wonrax/phobert-base-vietnamese-sentiment')"

# App code.
COPY . .

# Bake the knowledge_base + taxonomy ChromaDB index (chroma_db/) into the image.
RUN python knowledge_base/index.py

EXPOSE 8080
CMD ["python", "main.py"]
