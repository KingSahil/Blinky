from __future__ import annotations

import math
import re
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


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
    Lightweight SQLite & TF-IDF Cosine Similarity Vector Store for Desktop Python RAG.
    Indexes document text chunks and provides Top-K similarity search.
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
                    created_at REAL NOT NULL
                )
            """)
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
        Chunks document content and inserts chunks into SQLite vector store.
        """
        import time
        chunks = self.chunk_document(content, chunk_size=chunk_size, overlap=overlap)
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
                conn.execute(
                    """
                    INSERT INTO document_chunks (id, notebook_id, source_name, chunk_index, content, word_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (chunk_id, notebook_id, source_name, idx, chunk_text, word_count, now)
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
        Searches the vector store using cosine similarity and returns top-K matching chunks with similarity scores.
        Filters by active_sources if provided.
        """
        if active_sources is not None and not active_sources:
            return []

        query_tokens = simple_tokenize(query)
        if not query_tokens:
            return []
        query_tf = calculate_term_frequencies(query_tokens)

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

        results: List[Tuple[Dict[str, Any], float]] = []
        for row in rows:
            chunk_dict = dict(row)
            chunk_tokens = simple_tokenize(chunk_dict["content"])
            chunk_tf = calculate_term_frequencies(chunk_tokens)
            sim_score = cosine_similarity(query_tf, chunk_tf)
            if sim_score > 0.0:
                results.append((chunk_dict, round(sim_score, 4)))

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
