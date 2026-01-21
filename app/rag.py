import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from dotenv import load_dotenv

from app.utils import sanitize_text

load_dotenv()

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path("knowledge")


@dataclass
class RetrievedChunk:
    text: str
    score: float


class KeywordIndex:
    def __init__(self, chunks: List[str]) -> None:
        self.chunks = chunks
        self.chunk_tokens = [self._tokenize(chunk) for chunk in chunks]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token.lower() for token in text.split() if token.strip()}

    def search(self, query: str, top_k: int = 4) -> List[RetrievedChunk]:
        query_tokens = self._tokenize(query)
        scored: List[Tuple[int, float]] = []
        for idx, tokens in enumerate(self.chunk_tokens):
            if not tokens:
                continue
            overlap = query_tokens.intersection(tokens)
            score = len(overlap) / max(len(tokens), 1)
            if score > 0:
                scored.append((idx, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return [RetrievedChunk(text=self.chunks[idx], score=score) for idx, score in scored[:top_k]]


class RAGRetriever:
    def __init__(self, knowledge_dir: Path | None = None) -> None:
        self.knowledge_dir = knowledge_dir or KNOWLEDGE_DIR
        self.chunks = self._load_chunks()
        self.keyword_index = KeywordIndex(self.chunks)
        self.chroma = None
        self.collection = None
        self._init_vector_index()

    def _load_chunks(self) -> List[str]:
        chunks: List[str] = []
        for path in sorted(self.knowledge_dir.glob("**/*")):
            if path.suffix.lower() not in {".md", ".txt"}:
                continue
            content = path.read_text(encoding="utf-8")
            for raw_chunk in self._chunk_text(content):
                cleaned = sanitize_text(raw_chunk)
                if cleaned:
                    chunks.append(cleaned)
        logger.info("Loaded %s knowledge chunks", len(chunks))
        return chunks

    @staticmethod
    def _chunk_text(text: str) -> Iterable[str]:
        for block in text.split("\n\n"):
            trimmed = block.strip()
            if trimmed:
                yield trimmed

    def _init_vector_index(self) -> None:
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            logger.info("OPENAI_API_KEY missing. Using keyword search only.")
            return
        try:
            import chromadb
            from chromadb.utils import embedding_functions
        except ImportError:
            logger.warning("Chroma not available. Falling back to keyword search.")
            return

        model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.chroma = chromadb.Client()
        embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
            api_key=openai_key,
            model_name=model,
        )
        self.collection = self.chroma.get_or_create_collection(
            name="knowledge_base",
            embedding_function=embedding_fn,
        )
        if self.chunks:
            ids = [f"chunk-{idx}" for idx in range(len(self.chunks))]
            self.collection.add(documents=self.chunks, ids=ids)
            logger.info("Vector index initialized with %s chunks", len(self.chunks))

    def retrieve(self, query: str, top_k: int = 4) -> List[RetrievedChunk]:
        if self.collection is not None:
            result = self.collection.query(query_texts=[query], n_results=top_k)
            documents = result.get("documents", [[]])[0]
            distances = result.get("distances", [[]])[0]
            return [
                RetrievedChunk(text=doc, score=1.0 - distance)
                for doc, distance in zip(documents, distances)
                if doc
            ]
        return self.keyword_index.search(query, top_k=top_k)


retriever = RAGRetriever()
