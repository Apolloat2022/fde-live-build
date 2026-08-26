"""LLM + embedding providers with a deterministic offline fallback.

Why this exists: in a live assessment, a blocked corporate proxy or a rate
limit must not kill the demo. Every call site goes through these two
functions, so the whole system degrades to a local, dependency-free
implementation instead of raising.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import List

from app import config

_EMBED_DIM = 512


# ---------------------------------------------------------------- embeddings
def _hash_embed(text: str) -> List[float]:
    """Deterministic bag-of-words hashing embedding.

    Not semantically strong, but stable and dependency-free. Paired with BM25
    in hybrid retrieval it produces genuinely usable ranking offline.
    """
    vec = [0.0] * _EMBED_DIM
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    for tok in tokens:
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % _EMBED_DIM] += 1.0
        # Bigram-ish signal to reduce collisions.
        vec[(h >> 8) % _EMBED_DIM] += 0.5
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed_texts(texts: List[str]) -> List[List[float]]:
    if config.OFFLINE_MODE:
        return [_hash_embed(t) for t in texts]
    from langchain_openai import OpenAIEmbeddings

    client = OpenAIEmbeddings(model=config.EMBED_MODEL, api_key=config.OPENAI_API_KEY)
    return client.embed_documents(texts)


def embed_query(text: str) -> List[float]:
    return embed_texts([text])[0]


# ---------------------------------------------------------------------- chat
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
_CITE_PREFIX = re.compile(r"^\s*\[(S\d+)\]\s*(\([^)]*\))?\s*")


def _extractive_answer(prompt: str) -> str:
    """Offline 'generation': pick the context sentences that best overlap the
    question. Deterministic, grounded by construction, and honest about being
    extractive."""
    ctx_match = re.search(r"<context>(.*?)</context>", prompt, re.S)
    q_match = re.search(r"<question>(.*?)</question>", prompt, re.S)
    if not ctx_match or not q_match:
        return config.REFUSAL_TEXT
    context, question = ctx_match.group(1), q_match.group(1)
    q_terms = set(re.findall(r"[a-z0-9]{4,}", question.lower()))

    scored = []
    tag = None
    heading = ""
    for line in context.splitlines():
        m = _CITE_PREFIX.match(line)
        if m:
            # New source block. Capture the "(file § section)" provenance as
            # SCORING context only -- heading words like "Beneficial
            # Ownership" are how the user phrases the question, but they must
            # not be emitted as answer text.
            tag = m.group(1)
            heading = (m.group(2) or "").strip()
            body = line[m.end():].strip()
        else:
            body = line.strip()
        if not body:
            continue
        head_terms = set(re.findall(r"[a-z0-9]{4,}", heading.lower()))
        for sent in _SENT_SPLIT.split(body):
            sent = sent.strip()
            if len(sent) < 30:
                continue
            terms = set(re.findall(r"[a-z0-9]{4,}", sent.lower())) | head_terms
            overlap = len(q_terms & terms)
            if overlap:
                scored.append((overlap / (len(q_terms) or 1), sent, tag))

    scored.sort(key=lambda x: -x[0])
    if not scored:
        return config.REFUSAL_TEXT
    parts = []
    seen = set()
    for _, sent, tag in scored[:3]:
        if sent in seen:
            continue
        seen.add(sent)
        parts.append(f"{sent} [{tag}]" if tag else sent)
    return " ".join(parts)


def chat(prompt: str, system: str = "", temperature: float = 0.0) -> str:
    if config.OFFLINE_MODE:
        return _extractive_answer(prompt)
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=config.CHAT_MODEL,
        temperature=temperature,
        api_key=config.OPENAI_API_KEY,
    )
    messages = ([("system", system)] if system else []) + [("human", prompt)]
    return llm.invoke(messages).content.strip()


def provider_label() -> str:
    return "offline-deterministic" if config.OFFLINE_MODE else f"openai:{config.CHAT_MODEL}"
