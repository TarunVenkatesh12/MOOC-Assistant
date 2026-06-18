import re
import math
import pickle
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

THIS_DIR   = Path(__file__).parent
INDEX_PATH = THIS_DIR / "rag_index.pkl"

_INDEX:  Optional[Dict] = None
_MODEL              = None  # sentence-transformers model (lazy loaded)

MIN_SCORE_THRESHOLD = 0.25  # cosine similarity threshold (higher than TF-IDF's 0.01)


def _load_model(model_name: str):
    global _MODEL
    if _MODEL is None:
        logger.info(f"Loading embedding model: {model_name} ...")
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(model_name)
        logger.info("Embedding model loaded")
    return _MODEL


def _load_index(path: Path = INDEX_PATH) -> Dict:
    global _INDEX
    if _INDEX is None:
        if not path.exists():
            raise FileNotFoundError(
                f"RAG index not found at {path}.\n"
                "Run:  python build_rag.py   to build it first."
            )
        logger.info(f"Loading RAG index from {path} ...")
        with open(path, "rb") as f:
            _INDEX = pickle.load(f)

        index_type = _INDEX.get("index_type", "tfidf")
        n_chunks   = len(_INDEX["chunks"])

        if index_type == "semantic":
            emb_shape = _INDEX["embeddings"].shape
            logger.info(f"Semantic index loaded: {n_chunks:,} chunks, embeddings {emb_shape}")
        else:
            logger.info(f"TF-IDF index loaded: {n_chunks:,} chunks (rebuild recommended)")

    return _INDEX


def _save_index(path: Path = INDEX_PATH):
    global _INDEX
    if _INDEX is None:
        return
    with open(path, "wb") as f:
        pickle.dump(_INDEX, f, protocol=pickle.HIGHEST_PROTOCOL)
    size_mb = path.stat().st_size / 1_048_576
    logger.info(f"Index saved → {path} ({size_mb:.1f} MB)")


def _encode_query(query: str, model_name: str) -> np.ndarray:
    model = _load_model(model_name)
    vec   = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)
    return vec[0]  # shape: (D,)


def _is_semantic_index(index: Dict) -> bool:
    return index.get("index_type") == "semantic"


# ── TF-IDF fallback (kept for backward compatibility) ────────────────────────

def _tokenise(text: str) -> List[str]:
    STOPWORDS = {
        "bonjour","bonsoir","merci","votre","notre","vous","nous","pour","avec",
        "dans","sur","par","les","des","une","est","qui","que","pas","plus",
        "tout","bien","mais","donc","aussi","comme","sont","cette","cela","ça",
        "ca","ont","aux","au","du","de","le","la","et","en","un","il","elle",
        "the","and","for","with","that","this","from","have","are","not","but",
    }
    return [
        t for t in re.split(r"[^a-zA-ZÀ-ÿ0-9]+", text.lower())
        if len(t) > 2 and t not in STOPWORDS
    ]


def _tfidf_query_vector(query: str, vocab: Dict, idf: List[float]) -> Dict[int, float]:
    tokens = _tokenise(query)
    tf: Dict[str, int] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    total = max(len(tokens), 1)
    vec: Dict[int, float] = {}
    for term, count in tf.items():
        if term in vocab:
            idx = vocab[term]
            vec[idx] = (count / total) * idf[idx]
    return vec


def _cosine_sparse(a: Dict[int, float], b: Dict[int, float]) -> float:
    dot = sum(a[k] * b[k] for k in a if k in b)
    if dot == 0:
        return 0.0
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Main retrieve function ────────────────────────────────────────────────────

def retrieve(query: str, top_k: int = 8) -> List[Dict]:
    index = _load_index()

    if _is_semantic_index(index):
        # ── Semantic retrieval ────────────────────────────────────────────────
        model_name = index.get("model_name", "paraphrase-multilingual-MiniLM-L12-v2")
        q_vec      = _encode_query(query, model_name)  # shape (D,)
        embeddings = index["embeddings"]               # shape (N, D)
        chunks     = index["chunks"]

        # Cosine similarity — embeddings are already L2-normalised
        scores = embeddings @ q_vec  # shape (N,)

        # Filter by threshold and get top_k
        above_threshold = np.where(scores >= MIN_SCORE_THRESHOLD)[0]
        if len(above_threshold) == 0:
            # Relax threshold if nothing found
            above_threshold = np.argsort(scores)[::-1][:top_k]

        top_indices = above_threshold[np.argsort(scores[above_threshold])[::-1][:top_k]]

        results = []
        for idx in top_indices:
            results.append({
                **chunks[idx],
                "score": round(float(scores[idx]), 4),
            })

        logger.info(
            f"[Semantic] Retrieved {len(results)}/{top_k} chunks "
            f"(threshold={MIN_SCORE_THRESHOLD}) "
            f"for query: '{query[:60]}'"
        )
        return results

    else:
        # ── TF-IDF fallback ───────────────────────────────────────────────────
        vocab   = index["vocab"]
        idf     = index["idf"]
        vectors = index["vectors"]
        chunks  = index["chunks"]

        q_vec = _tfidf_query_vector(query, vocab, idf)
        if not q_vec:
            return []

        scored = []
        for i, (chunk, c_vec) in enumerate(zip(chunks, vectors)):
            score = _cosine_sparse(q_vec, c_vec)
            if score >= 0.01:
                scored.append((score, i))

        scored.sort(reverse=True)
        results = []
        for score, i in scored[:top_k]:
            results.append({**chunks[i], "score": round(score, 4)})

        logger.info(f"[TF-IDF fallback] Retrieved {len(results)} chunks for: '{query[:60]}'")
        return results


def retrieve_as_context(query: str, top_k: int = 8, max_chars: int = 4000) -> str:
    all_chunks = retrieve(query, top_k=top_k * 2)

    if not all_chunks:
        return "Aucun contenu pertinent trouvé dans les ressources du cours."

    course_chunks = [c for c in all_chunks if c.get("kind") != "forum_post"]
    forum_chunks  = [c for c in all_chunks if c.get("kind") == "forum_post"]
    reranked      = course_chunks[:top_k] + forum_chunks[:3]

    parts = []
    total = 0
    for chunk in reranked:
        kind_label = "Forum" if chunk.get("kind") == "forum_post" else "Cours"
        block = f"[{kind_label} | score: {chunk['score']}]\n{chunk['text']}"
        if total + len(block) > max_chars:
            remaining = max_chars - total
            if remaining > 100:
                parts.append(block[:remaining] + "…")
            break
        parts.append(block)
        total += len(block)

    return "\n\n---\n\n".join(parts)


def add_forum_posts_to_index(posts: List[Dict], topic_title: str,
                              path: Path = INDEX_PATH) -> int:
    index = _load_index(path)

    if not _is_semantic_index(index):
        logger.warning("Index is TF-IDF — forum posts not added (rebuild index first)")
        return 0

    model_name  = index.get("model_name", "paraphrase-multilingual-MiniLM-L12-v2")
    chunks      = index["chunks"]
    embeddings  = index["embeddings"]

    existing_sources = {c["source"] for c in chunks}
    new_texts, new_chunks = [], []
    chunk_size, chunk_overlap = 800, 200

    for post in posts:
        author  = post.get("author", "inconnu")
        content = post.get("content", "").strip()
        ai_resp = post.get("ai_response", "")

        if not content:
            continue

        text_parts = [f"[FORUM] {topic_title} — {author}: {content}"]
        if ai_resp and ai_resp != "None":
            text_parts.append(f"Réponse pédagogique: {ai_resp}")
        full_text = " ".join(text_parts)

        start, chunk_idx = 0, 0
        while start < len(full_text):
            chunk_text = full_text[start:start + chunk_size]
            source_key = f"forum/{topic_title[:40]}/{author}/{chunk_idx}"

            if source_key not in existing_sources:
                new_texts.append(chunk_text)
                new_chunks.append({
                    "text":     chunk_text,
                    "source":   source_key,
                    "kind":     "forum_post",
                    "chunk_id": chunk_idx,
                })
                existing_sources.add(source_key)

            start += chunk_size - chunk_overlap
            chunk_idx += 1

    if not new_texts:
        logger.info("No new forum chunks to add (all already indexed)")
        return 0

    model      = _load_model(model_name)
    new_embeds = model.encode(new_texts, convert_to_numpy=True,
                               normalize_embeddings=True, show_progress_bar=False)

    index["embeddings"] = np.vstack([embeddings, new_embeds])
    index["chunks"].extend(new_chunks)

    logger.info(f"Added {len(new_chunks)} forum chunks to index")
    _save_index(path)
    return len(new_chunks)


if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) or "Comment utiliser MicroPython avec GPIO ?"
    print(f"\nQuery: {query}\n{'─'*60}")
    for r in retrieve(query, top_k=5):
        kind = r.get("kind", "?")
        print(f"\n  Score: {r['score']}  |  [{kind}]  {r['source']}")
        print(f"  {r['text'][:200]}…")
    print()