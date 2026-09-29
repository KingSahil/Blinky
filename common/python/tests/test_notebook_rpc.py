import unittest
from pathlib import Path
from main import handle_notebook_rpc, run_notebook_intelligence


class TestNotebookRPC(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("tmp") / "notebooks"
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def test_notebook_rpc_flow(self):
        # 1. Create Notebook
        res_create = handle_notebook_rpc("notebook_create", {"title": "Physics Notes", "description": "Mechanics"})
        self.assertTrue(res_create["success"])
        nb_id = res_create["notebook"]["id"]

        # 2. Add Source
        res_source = handle_notebook_rpc(
            "notebook_add_source",
            {
                "notebook_id": nb_id,
                "source_name": "newton.txt",
                "content": "Newton's second law is F = ma.",
                "file_type": "txt",
            }
        )
        self.assertTrue(res_source["success"])
        self.assertEqual(res_source["source"]["source_name"], "newton.txt")

        # 3. List Notebooks
        res_list = handle_notebook_rpc("notebook_list", {})
        self.assertTrue(res_list["success"])
        self.assertGreaterEqual(len(res_list["notebooks"]), 1)

        # 4. Sync API Keys
        res_keys = handle_notebook_rpc("sync_api_keys", {})
        self.assertTrue(res_keys["success"])
        self.assertIn("groq_key", res_keys["keys"])

        # 5. Delete Notebook
        res_del = handle_notebook_rpc("notebook_delete", {"notebook_id": nb_id})
        self.assertTrue(res_del["success"])


if __name__ == "__main__":
    unittest.main()
