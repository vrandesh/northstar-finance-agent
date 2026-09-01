""" RAG Retrieval over the corpus of markdown documents.

    To keep the whole implementation deterministic and since the corpus is tiny
    Load the corpus of markdown documents and split them into chunks.
    Returns: Two List come back : Everything retrieved and only eligible current policy
        retrieved (list[RetrievedChunk]): All retrieved chunks, for transparency.
        eligible (list[RetrievedChunk]): Only chunks that are currently eligible according to the policy.
"""
import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from .config import CORPUS_DIR
from .schemas import Citation, RetrievedChunk

_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING = re.compile(r"^##\s+(.*)$", re.MULTILINE)
_WORD = re.compile(r"[a-z0-9]+")


@dataclass
class Chunk:
    doc_id: str
    version: str
    status: str
    section: str
    text: str


@dataclass
class Retrieval:
    retrieved: list[RetrievedChunk]
    eligible: list[RetrievedChunk]


def _read_meta(block: str) -> dict:
    meta = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()
    return meta


def _status_of(meta: dict) -> str:
    if meta.get("status") == "untrusted" or meta.get("classification", "").startswith("external"):
        return "untrusted"
    if meta.get("status") == "superseded":
        return "superseded"
    return "current"


def load_corpus() -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        m = _FRONT_MATTER.match(raw)
        meta = _read_meta(m.group(1)) if m else {}
        body = raw[m.end():] if m else raw
        doc_id = meta.get("document_id", path.stem)
        version = meta.get("version", "0")
        status = _status_of(meta)
        headings = list(_HEADING.finditer(body))
        if not headings:
            chunks.append(Chunk(doc_id, version, status, "full", body.strip()))
            continue
        for i, h in enumerate(headings):
            end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
            chunks.append(Chunk(doc_id, version, status, f"§{i + 1} {h.group(1).strip()}",
                                body[h.start():end].strip()))
    return chunks


class Retriever:
    def __init__(self, chunks: list[Chunk] | None = None) -> None:
        self.chunks = chunks or load_corpus()
        self._bm25 = BM25Okapi([_WORD.findall(c.text.lower()) for c in self.chunks])

    def search(self, query: str, k: int = 8, force_include: list[str] | None = None) -> Retrieval:
        scores = self._bm25.get_scores(_WORD.findall(query.lower()))
        top = max(scores) or 1.0
        ranked = sorted(zip(scores, self.chunks), key=lambda x: x[0], reverse=True)

        retrieved = [self._chunk(s / top, c) for s, c in ranked[:k]]
        for doc_id in force_include or []:
            if not any(rc.doc_id == doc_id for rc in retrieved):
                hit = next(((s, c) for s, c in ranked if c.doc_id == doc_id), None)
                if hit:
                    retrieved.append(self._chunk(hit[0] / top, hit[1]))

        eligible = [self._chunk(s / top, c) for s, c in ranked if c.status == "current"][:k]
        return Retrieval(retrieved=retrieved, eligible=eligible)

    @staticmethod
    def _chunk(rel: float, c: Chunk) -> RetrievedChunk:
        return RetrievedChunk(
            doc_id=c.doc_id, version=c.version, status=c.status, section=c.section,
            text=c.text, relevance=round(float(rel), 4), trusted=(c.status == "current"),
            citation=Citation(doc_id=c.doc_id, version=c.version, section=c.section))
