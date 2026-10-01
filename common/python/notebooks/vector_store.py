from __future__ import annotations

import math
import re
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
from utils.logging import get_logger

LOGGER = get_logger("blinky.vector_store")

_EMBEDDING_MODEL: Any = None


def get_embedding_model():
    """Lazily loads the local FastEmbed ONNX embedding model (bge-small-en-v1.5)."""
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        try:
            from fastembed import TextEmbedding
            _EMBEDDING_MODEL = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            LOGGER.info("FastEmbed neural embedding model initialized successfully.")
        except Exception as exc:
            LOGGER.warning("FastEmbed not available, falling back to lexical search: %s", exc)
            _EMBEDDING_MODEL = False
    return _EMBEDDING_MODEL if _EMBEDDING_MODEL is not False else None


def serialize_vector(vec: Any) -> bytes:
    """Converts a vector to raw float32 bytes for SQLite BLOB storage."""
    arr = np.asarray(vec, dtype=np.float32)
    return arr.tobytes()


def deserialize_vector(blob: bytes) -> np.ndarray:
    """Converts SQLite BLOB bytes back to a numpy float32 array."""
    return np.frombuffer(blob, dtype=np.float32)


def simple_tokenize(text: str) -> List[str]:
    """Tokenizes text into lowercase alphanumeric words."""
    return re.findall(r'\b\w+\b', text.lower())


def calculate_term_frequencies(tokens: List[str]) -> Dict[str, float]:
    """Calculates normalized term frequency (TF) for a token list."""
    if not tokens:
        return {}
    counts: Dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    total = len(tokens)
    return {word: count / total for word, count in counts.items()}


def cosine_similarity(tf1: Dict[str, float], tf2: Dict[str, float]) -> float:
    """Computes cosine similarity between two term-frequency vector dictionaries."""
    if not tf1 or not tf2:
        return 0.0
    
    # Intersection of keys
    common = set(tf1.keys()).intersection(set(tf2.keys()))
    if not common:
        return 0.0
    
    dot_product = sum(tf1[word] * tf2[word] for word in common)
    mag1 = math.sqrt(sum(val ** 2 for val in tf1.values()))
    mag2 = math.sqrt(sum(val ** 2 for val in tf2.values()))
    
    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0
    return dot_product / (mag1 * mag2)


class VectorStore:
    """
    Neural + Hybrid SQLite Vector Store for Desktop Python RAG.
    Indexes document text chunks with FastEmbed dense neural vectors (384-d),
    providing semantic understanding, synonym matching, and hybrid lexical fallbacks.
    """

    def __init__(self, db_path: Optional[Path | str] = None):
        if db_path is None:
            db_path = Path("tmp") / "notebooks" / "vector_store.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id TEXT PRIMARY KEY,
                    notebook_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    word_count INTEGER NOT NULL,
                    embedding BLOB,
                    created_at REAL NOT NULL
                )
            """)
            # Ensure schema migration for existing databases without embedding column
            try:
                conn.execute("ALTER TABLE document_chunks ADD COLUMN embedding BLOB")
            except sqlite3.OperationalError:
                pass
            conn.commit()

    def chunk_document(self, content: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
        """Splits document content into overlapping word chunks."""
        words = content.split()
        if not words:
            return []
        
        chunks = []
        step = max(1, chunk_size - overlap)
        for i in range(0, len(words), step):
            chunk_words = words[i:i + chunk_size]
            chunks.append(" ".join(chunk_words))
            if i + chunk_size >= len(words):
                break
        return chunks

    def index_document(
        self,
        notebook_id: str,
        source_name: str,
        content: str,
        chunk_size: int = 512,
        overlap: int = 64
    ) -> List[Dict[str, Any]]:
        """
        Chunks document content, generates FastEmbed neural dense embeddings,
        and inserts chunks into SQLite vector store.
        """
        import time
        chunks = self.chunk_document(content, chunk_size=chunk_size, overlap=overlap)
        if not chunks:
            return []

        # Attempt neural dense embedding generation
        model = get_embedding_model()
        dense_embeddings = None
        if model is not None:
            try:
                dense_embeddings = list(model.embed(chunks))
            except Exception as e:
                LOGGER.warning("Could not generate dense embeddings for '%s': %s", source_name, e)

        records = []
        now = time.time()

        with self._get_connection() as conn:
            # Delete any pre-existing chunks for this source in notebook
            conn.execute(
                "DELETE FROM document_chunks WHERE notebook_id = ? AND source_name = ?",
                (notebook_id, source_name)
            )
            for idx, chunk_text in enumerate(chunks):
                chunk_id = f"vchunk_{notebook_id}_{hash(source_name)}_{idx}_{int(now)}"
                word_count = len(chunk_text.split())
                emb_blob = (
                    serialize_vector(dense_embeddings[idx])
                    if (dense_embeddings is not None and idx < len(dense_embeddings))
                    else None
                )
                conn.execute(
                    """
                    INSERT INTO document_chunks (id, notebook_id, source_name, chunk_index, content, word_count, embedding, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (chunk_id, notebook_id, source_name, idx, chunk_text, word_count, emb_blob, now)
                )
                records.append({
                    "id": chunk_id,
                    "notebook_id": notebook_id,
                    "source_name": source_name,
                    "chunk_index": idx,
                    "content": chunk_text,
                    "word_count": word_count
                })
            conn.commit()
        return records

    def search_top_k(
        self,
        notebook_id: str,
        query: str,
        top_k: int = 5,
        active_sources: Optional[List[str]] = None
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Searches the vector store using FastEmbed Neural Cosine Similarity with lexical fallback.
        Filters by active_sources if provided.
        """
        if active_sources is not None and not active_sources:
            return []

        query_str = (query or "").strip()
        if not query_str:
            return []

        with self._get_connection() as conn:
            if active_sources is not None:
                placeholders = ",".join("?" for _ in active_sources)
                params: List[Any] = [notebook_id] + list(active_sources)
                cursor = conn.execute(
                    f"SELECT * FROM document_chunks WHERE notebook_id = ? AND source_name IN ({placeholders})",
                    params
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM document_chunks WHERE notebook_id = ?",
                    (notebook_id,)
                )
            rows = cursor.fetchall()

        if not rows:
            return []

        # Generate query dense embedding if neural model is available
        model = get_embedding_model()
        query_vec: Optional[np.ndarray] = None
        if model is not None:
            try:
                embeddings_gen = model.query_embed([query_str])
                query_vec = np.asarray(next(embeddings_gen), dtype=np.float32)
            except Exception as e:
                LOGGER.warning("Could not embed query '%s' with neural model: %s", query_str, e)

        query_tokens = simple_tokenize(query_str)
        query_tf = calculate_term_frequencies(query_tokens) if query_tokens else {}

        results: List[Tuple[Dict[str, Any], float]] = []
        for row in rows:
            chunk_dict = dict(row)
            emb_blob = chunk_dict.pop("embedding", None)

            neural_sim: Optional[float] = None
            if query_vec is not None and emb_blob is not None:
                try:
                    chunk_vec = deserialize_vector(emb_blob)
                    # Dense vectors from fastembed are normalized, so dot product == cosine similarity
                    neural_sim = float(np.dot(query_vec, chunk_vec))
                except Exception:
                    neural_sim = None

            # Calculate lexical TF cosine similarity
            lexical_sim = 0.0
            if query_tf:
                chunk_tokens = simple_tokenize(chunk_dict["content"])
                chunk_tf = calculate_term_frequencies(chunk_tokens)
                lexical_sim = cosine_similarity(query_tf, chunk_tf)

            # Score determination:
            # If neural embedding is available, use semantic similarity (with lexical bonus if exact keywords match)
            if neural_sim is not None:
                # Dense similarity is between [-1, 1]. Relevant matches usually > 0.4.
                # Blend 80% neural semantic match with 20% exact keyword match
                final_score = max(neural_sim, (neural_sim * 0.8) + (lexical_sim * 0.2))
            else:
                final_score = lexical_sim

            if final_score > 0.05:
                results.append((chunk_dict, round(final_score, 4)))

        # Sort descending by similarity score
        results.sort(key=lambda item: item[1], reverse=True)
        return results[:top_k]

    def delete_source(self, notebook_id: str, source_name: str) -> None:
        """Removes all indexed chunks for a single source."""
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM document_chunks WHERE notebook_id = ? AND source_name = ?",
                (notebook_id, source_name)
            )
            conn.commit()

    def clear_notebook(self, notebook_id: str) -> None:
        """Removes all indexed vector chunks for a given notebook."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM document_chunks WHERE notebook_id = ?", (notebook_id,))
            conn.commit()
