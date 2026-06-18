import re
import pickle
import logging
import numpy as np
from pathlib import Path
from html.parser import HTMLParser
from typing import List, Dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
logger = logging.getLogger(__name__)

THIS_DIR   = Path(__file__).parent
ROOT_DIR   = THIS_DIR.parent
COURSE_DIR = ROOT_DIR / "course_data"
INDEX_PATH = THIS_DIR / "rag_index.pkl"

CHUNK_SIZE    = 600
CHUNK_OVERLAP = 150
MAX_DOC_CHARS = 50_000

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


class _StripHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: List[str] = []

    def handle_data(self, data: str):
        s = data.strip()
        if s:
            self._parts.append(s)

    def get_text(self) -> str:
        return " ".join(self._parts)


def html_to_text(html: str) -> str:
    parser = _StripHTML()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.get_text()


def xml_to_text(xml: str) -> str:
    parts: List[str] = []

    for attr in ("display_name", "title", "label"):
        for m in re.finditer(rf'{attr}="([^"]+)"', xml):
            val = m.group(1).strip()
            if len(val) > 3 and val.lower() != "null":
                parts.append(val)

    for m in re.finditer(r'markdown="([^"]+)"', xml, re.DOTALL):
        raw = m.group(1)
        if raw.strip().lower() == "null":
            continue
        raw = raw.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
        raw = re.sub(r"&#10;", "\n", raw)
        raw = re.sub(r">>(.*?)<<", r"\1", raw, flags=re.DOTALL)
        raw = re.sub(r"\[explanation\]", " Explication: ", raw)
        raw = re.sub(r"\[/explanation\]", " ", raw)
        parts.append(raw.strip())

    for m in re.finditer(r"<html[^>]*>(.*?)</html>", xml, re.DOTALL):
        t = html_to_text(m.group(1))
        if len(t) > 10:
            parts.append(t)

    for m in re.finditer(r"<problem[^>]*>(.*?)</problem>", xml, re.DOTALL):
        t = html_to_text(m.group(1))
        if len(t) > 10:
            parts.append(t)

    for tag in ("optioninput", "choicegroup", "stringresponse",
                "numericalresponse", "multiplechoiceresponse"):
        for m in re.finditer(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.DOTALL):
            t = html_to_text(m.group(1))
            if len(t) > 3:
                parts.append(t)

    for tag in ("choice", "option", "solution", "p", "label",
                "description", "explanation", "hint", "demandhint",
                "correct_hint", "additional_answer"):
        for m in re.finditer(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.DOTALL):
            t = html_to_text(m.group(1))
            if len(t) > 3:
                parts.append(t)

    if not parts:
        fallback = html_to_text(xml)
        if len(fallback) > 40:
            parts.append(fallback)

    seen, unique = set(), []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            unique.append(p)

    return " ".join(unique)


def collect_documents(course_dir: Path) -> List[Dict]:
    docs: List[Dict] = []

    def _add(text: str, source: str, kind: str):
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > MAX_DOC_CHARS:
            text = text[:MAX_DOC_CHARS]
        if len(text) > 40:
            docs.append({"text": text, "source": source, "kind": kind})

    html_kept = 0
    for html_file in course_dir.rglob("*.html"):
        try:
            raw  = html_file.read_text(encoding="utf-8", errors="replace")
            text = html_to_text(raw)
            if len(text.strip()) > 40:
                _add(text, str(html_file.relative_to(course_dir)), "html_lesson")
                html_kept += 1
        except Exception as e:
            logger.warning(f"  Skip {html_file}: {e}")

    logger.info(f"  HTML: {html_kept} kept")

    xml_kept = 0
    for xml_file in course_dir.rglob("*.xml"):
        try:
            raw = xml_file.read_text(encoding="utf-8", errors="replace")
            if len(raw) < 40:
                continue
            text = xml_to_text(raw)
            if text and len(text.strip()) > 40:
                _add(text, str(xml_file.relative_to(course_dir)), "xml_problem")
                xml_kept += 1
        except Exception as e:
            logger.warning(f"  Skip {xml_file}: {e}")

    logger.info(f"  XML : {xml_kept} kept")
    logger.info(f"Collected {len(docs)} raw documents total")
    return docs


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    chunks: List[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return chunks


def build_chunks(docs: List[Dict]) -> List[Dict]:
    chunks: List[Dict] = []
    for doc in docs:
        for i, chunk in enumerate(chunk_text(doc["text"])):
            chunks.append({
                "text":     chunk,
                "source":   doc["source"],
                "kind":     doc["kind"],
                "chunk_id": i,
            })
    logger.info(f"Built {len(chunks)} chunks from {len(docs)} documents")
    return chunks


def build_semantic_index(chunks: List[Dict]) -> Dict:
    logger.info(f"Loading embedding model: {EMBEDDING_MODEL} ...")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(EMBEDDING_MODEL)
    except ImportError:
        raise ImportError(
            "sentence-transformers not installed.\n"
            "Run: pip install sentence-transformers"
        )

    texts = [c["text"] for c in chunks]
    logger.info(f"Encoding {len(texts)} chunks ...")
    embeddings = model.encode(texts, batch_size=64, show_progress_bar=True,
                               convert_to_numpy=True, normalize_embeddings=True)

    logger.info(f"  Embedding shape: {embeddings.shape}")
    return {
        "chunks":     chunks,
        "embeddings": embeddings,   # shape: (N, D) float32 numpy array
        "model_name": EMBEDDING_MODEL,
        "index_type": "semantic",
    }


def save_index(index: Dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(index, f, protocol=pickle.HIGHEST_PROTOCOL)
    size_mb = path.stat().st_size / 1_048_576
    logger.info(f"Index saved → {path}  ({size_mb:.1f} MB)")


def build_index(course_dir: Path = COURSE_DIR, index_path: Path = INDEX_PATH) -> Dict:
    if not course_dir.exists():
        raise FileNotFoundError(
            f"Course directory not found: {course_dir}\n"
            "Extract the tar.gz there, or update COURSE_DIR in rag/ingest.py"
        )
    logger.info(f"Reading course from : {course_dir}")
    docs   = collect_documents(course_dir)
    chunks = build_chunks(docs)
    index  = build_semantic_index(chunks)
    save_index(index, index_path)
    return index


if __name__ == "__main__":
    build_index()
    print("\n  Semantic RAG index built — run your dashboard now!")