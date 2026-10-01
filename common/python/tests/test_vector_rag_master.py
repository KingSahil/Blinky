import unittest
import os
import json
import base64
from pathlib import Path

from notebooks.vector_store import VectorStore, simple_tokenize, calculate_term_frequencies, cosine_similarity
from notebooks.okf_context_builder import build_okf_prompt_context
from notebooks.notebook_manager import NotebookManager
from main import handle_notebook_rpc


class TestVectorRAGMaster(unittest.TestCase):
    """
    Master Integration Test Suite for Desktop & Mobile Vector Database RAG and Encrypted Key Sync.
    """

    def setUp(self):
        self.test_dir = Path("tmp") / "test_vector_rag_master"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.test_dir / "vector_store.db"
        self.vector_store = VectorStore(db_path=self.db_path)
        self.manager = NotebookManager(storage_dir=self.test_dir)

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_tokenization_and_tf_idf_similarity(self):
        tokens_a = simple_tokenize("Python machine learning vector search engine")
        tokens_b = simple_tokenize("Vector search cosine similarity in Python")
        tf_a = calculate_term_frequencies(tokens_a)
        tf_b = calculate_term_frequencies(tokens_b)
        sim = cosine_similarity(tf_a, tf_b)
        self.assertGreater(sim, 0.25)

    def test_02_vector_indexing_and_top_k_retrieval(self):
        nb = self.manager.create_notebook("AI Research Hub", "Deep Learning Docs")
        nb_id = nb["id"]

        doc_content = (
            "Neural networks use gradient descent optimization. "
            "Transformers utilize self-attention mechanisms for natural language processing tasks. "
            "Convolutional neural networks are specialized for computer vision image classification."
        )

        records = self.vector_store.index_document(
            notebook_id=nb_id,
            source_name="deep_learning.txt",
            content=doc_content,
            chunk_size=10,
            overlap=2
        )
        self.assertGreater(len(records), 0)

        matches = self.vector_store.search_top_k(
            notebook_id=nb_id,
            query="attention mechanisms natural language",
            top_k=2
        )
        self.assertGreater(len(matches), 0)
        top_match, score = matches[0]
        self.assertEqual(top_match["source_name"], "deep_learning.txt")
        self.assertGreater(score, 0.0)

    def test_03_hybrid_context_builder_with_vector_matches(self):
        nb = self.manager.create_notebook("Robotics")
        matches = [
            ({
                "source_name": "kinematics.pdf",
                "chunk_index": 0,
                "content": "Inverse kinematics calculates joint angles for target end-effector positions."
            }, 0.91)
        ]
        context = build_okf_prompt_context(nb, "How do joint angles get calculated?", vector_matches=matches)
        self.assertIn("kinematics.pdf", context["user_prompt"])
        self.assertIn("91%", context["user_prompt"])
        self.assertEqual(context["source_count"], 1)

    def test_04_encrypted_api_key_sync_handshake(self):
        os.environ["GROQ_API_KEY"] = "gsk_mock_test_key_12345"
        res = handle_notebook_rpc("sync_api_keys", {})
        self.assertTrue(res["success"])
        self.assertEqual(res["keys"]["groq_key"], "gsk_mock_test_key_12345")
        self.assertIn("encoded_payload", res)
        self.assertIn("synced_at", res)

        # Verify base64 payload decoding
        decoded_bytes = base64.b64decode(res["encoded_payload"])
        decoded_keys = json.loads(decoded_bytes.decode("utf-8"))
        self.assertEqual(decoded_keys["groq_key"], "gsk_mock_test_key_12345")


if __name__ == "__main__":
    unittest.main()
