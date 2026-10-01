import unittest
from pathlib import Path
from notebooks.vector_store import VectorStore, simple_tokenize, calculate_term_frequencies, cosine_similarity
from notebooks.okf_context_builder import build_okf_prompt_context


class TestVectorStore(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("tmp") / "test_vector_store"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.test_dir / "vector_store.db"
        self.store = VectorStore(db_path=self.db_path)

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_tokenization_and_similarity(self):
        tokens1 = simple_tokenize("Python programming language for AI")
        tokens2 = simple_tokenize("AI Python development and language models")
        tf1 = calculate_term_frequencies(tokens1)
        tf2 = calculate_term_frequencies(tokens2)
        sim = cosine_similarity(tf1, tf2)
        self.assertGreater(sim, 0.3)

    def test_document_chunking(self):
        long_text = "word " * 1200
        chunks = self.store.chunk_document(long_text, chunk_size=512, overlap=64)
        self.assertGreater(len(chunks), 1)

    def test_indexing_and_top_k_search(self):
        doc_content = (
            "Python is a popular programming language used for machine learning, artificial intelligence, "
            "and web development. Tauri provides desktop shell capabilities with Rust and React."
        )
        records = self.store.index_document(
            notebook_id="nb_test_1",
            source_name="guide.txt",
            content=doc_content,
            chunk_size=10,
            overlap=2
        )
        self.assertGreater(len(records), 0)

        # Search for Python machine learning
        results = self.store.search_top_k("nb_test_1", "Python machine learning", top_k=3)
        self.assertGreater(len(results), 0)
        top_match, score = results[0]
        self.assertIn("guide.txt", top_match["source_name"])
        self.assertGreater(score, 0.0)

    def test_okf_context_builder_with_vector_matches(self):
        doc_match = ({
            "source_name": "ai_manual.pdf",
            "chunk_index": 0,
            "content": "Deep learning models require GPU memory allocation."
        }, 0.85)
        
        context = build_okf_prompt_context(
            notebook={"sources": []},
            query="GPU requirements?",
            vector_matches=[doc_match]
        )
        self.assertIn("VECTOR CHUNK: ai_manual.pdf", context["user_prompt"])
        self.assertIn("85%", context["user_prompt"])
        self.assertEqual(context["source_count"], 1)


if __name__ == "__main__":
    unittest.main()
