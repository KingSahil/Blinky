import unittest
from pathlib import Path
from notebooks.document_parser import parse_source_to_okf
from notebooks.notebook_manager import NotebookManager
from notebooks.okf_context_builder import build_okf_prompt_context


class TestNotebookOKF(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("tmp") / "test_notebooks"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.manager = NotebookManager(storage_dir=self.test_dir)

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_parse_text_source_to_okf(self):
        raw_text = "# VS Code Tips\n- Press Ctrl+Shift+P to open Command Palette."
        res = parse_source_to_okf("vscode_tips.md", raw_text, file_type="md")
        self.assertEqual(res["source_name"], "vscode_tips.md")
        self.assertIn("### SOURCE: vscode_tips.md", res["okf_content"])
        self.assertIn("Ctrl+Shift+P", res["okf_content"])

    def test_notebook_crud(self):
        nb = self.manager.create_notebook("Project Blinky Notes", "AI Assistant Architecture")
        self.assertIsNotNone(nb["id"])

        src = self.manager.add_source_to_notebook(
            nb["id"],
            "architecture.md",
            "# Blinky Architecture\nUses Tauri, React 19, and Python AI daemon.",
            file_type="md"
        )
        self.assertIsNotNone(src)
        self.assertEqual(src["source_name"], "architecture.md")

        fetched = self.manager.get_notebook(nb["id"])
        self.assertEqual(len(fetched["sources"]), 1)

    def test_okf_context_builder(self):
        nb = self.manager.create_notebook("Research")
        self.manager.add_source_to_notebook(
            nb["id"],
            "manual.txt",
            "To split window in VS Code, press Ctrl+\\.",
            file_type="txt"
        )
        fetched = self.manager.get_notebook(nb["id"])
        context = build_okf_prompt_context(fetched, "How do I split editor?")
        self.assertIn("grounded", context["system_prompt"].lower())
        self.assertIn("manual.txt", context["user_prompt"])
        self.assertIn("Ctrl+\\", context["user_prompt"])


if __name__ == "__main__":
    unittest.main()
