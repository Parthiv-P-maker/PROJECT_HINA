"""
Semantic recall: pick the remembered facts closest in meaning to what the user said.

Embeddings come from Ollama (EMBED_MODEL, default nomic-embed-text) and are cached
next to each fact in the memory database, so a fact is embedded once. Everything
degrades quietly: no Ollama, or the embedding model not pulled, returns None and
the caller uses the keyword matching in core/memory_store.py.
"""

import json
import math

import requests

from core import ai_engine, memory_store
from utils.logger import get_logger

logger = get_logger(__name__)

EMBED_URL = "http://localhost:11434/api/embed"
EMBED_TIMEOUT = 20
MIN_SIMILARITY = 0.45   # nomic-embed-text scores related text around 0.5-0.8
# nomic-embed-text wants a task prefix on its inputs
QUERY_PREFIX, DOCUMENT_PREFIX = "search_query: ", "search_document: "


def available():
    """Ollama is up and the embedding model is installed."""
    if not ai_engine.ollama_available():
        return False
    models = ai_engine._health.get("models")
    return bool(models) and ai_engine.model_installed(ai_engine.EMBED_MODEL)


def embed(texts, prefix=DOCUMENT_PREFIX):
    """One vector per text, or None if embeddings aren't available."""
    texts = list(texts)
    if not texts:
        return []
    if not available():
        return None
    try:
        response = requests.post(EMBED_URL, json={"model": ai_engine.EMBED_MODEL,
                                                  "input": [prefix + t for t in texts]},
                                 timeout=EMBED_TIMEOUT)
        response.raise_for_status()
        vectors = response.json().get("embeddings")
        if isinstance(vectors, list) and len(vectors) == len(texts):
            return vectors
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
    return None


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def relevant_facts(text, limit=5, always_if_at_most=6):
    """Facts closest in meaning to `text`, best first; None when embeddings aren't available.

    With only a few facts they all fit in the prompt, so nothing is embedded.
    """
    facts = memory_store.list_facts()
    if len(facts) <= always_if_at_most:
        return facts
    if not available():
        return None

    missing = [f for f in facts if not f.get("embedding")]
    if missing:
        vectors = embed([f["text"] for f in missing])
        if vectors is None:
            return None
        for fact, vector in zip(missing, vectors):
            fact["embedding"] = json.dumps(vector)
            memory_store.set_fact_embedding(fact["id"], vector)

    query = embed([text], prefix=QUERY_PREFIX)
    if not query:
        return None
    scored = [(cosine(query[0], json.loads(f["embedding"])), f) for f in facts]
    scored.sort(key=lambda s: -s[0])
    return [f for score, f in scored if score >= MIN_SIMILARITY][:limit]
