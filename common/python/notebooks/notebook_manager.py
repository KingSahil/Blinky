from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from utils.logging import get_logger
from .document_parser import parse_source_to_okf

LOGGER = get_logger("blinky.notebook_manager")
NOTEBOOKS_DIR = Path("tmp") / "notebooks"


class NotebookManager:
    """JSON-backed CRUD manager for user Knowledge Notebooks and attached document sources."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or NOTEBOOKS_DIR
        self.store_file = self.storage_dir / "notebooks_store.json"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.data: Dict[str, Dict[str, Any]] = self._load_store()

    def _load_store(self) -> Dict[str, Dict[str, Any]]:
        if not self.store_file.exists():
            return {}
        try:
            content = self.store_file.read_text(encoding="utf-8")
            return json.loads(content)
        except Exception as e:
            LOGGER.error(f"Failed loading notebook store: {e}")
            return {}

    def _save_store(self) -> None:
        try:
            self.store_file.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        except Exception as e:
            LOGGER.error(f"Failed saving notebook store: {e}")

    def create_notebook(self, title: str, description: str = "") -> Dict[str, Any]:
        notebook_id = f"nb_{uuid.uuid4().hex[:8]}"
        now = int(time.time())
        notebook = {
            "id": notebook_id,
            "title": title.strip() or "Untitled Notebook",
            "description": description.strip(),
            "created_at": now,
            "updated_at": now,
            "sources": [],
            "history": [],
        }
        self.data[notebook_id] = notebook
        self._save_store()
        LOGGER.info(f"Created notebook: {title} ({notebook_id})")
        return notebook

    def list_notebooks(self) -> List[Dict[str, Any]]:
        return sorted(list(self.data.values()), key=lambda x: x.get("updated_at", 0), reverse=True)

    def get_notebook(self, notebook_id: str) -> Optional[Dict[str, Any]]:
        return self.data.get(notebook_id)

    def add_source_to_notebook(
        self,
        notebook_id: str,
        source_name: str,
        content: str | bytes,
        file_type: str = "txt"
    ) -> Optional[Dict[str, Any]]:
        notebook = self.get_notebook(notebook_id)
        if not notebook:
            LOGGER.warning(f"Notebook {notebook_id} not found")
            return None

        parsed = parse_source_to_okf(source_name, content, file_type=file_type)
        source_id = f"src_{uuid.uuid4().hex[:8]}"
        source_entry = {
            "id": source_id,
            "source_name": parsed["source_name"],
            "file_type": parsed["file_type"],
            "word_count": parsed["word_count"],
            "char_count": parsed["char_count"],
            "okf_content": parsed["okf_content"],
            "raw_text": parsed["raw_text"],
            "active": True,
            "created_at": int(time.time()),
        }

        # Deduplicate sources by name
        notebook["sources"] = [s for s in notebook["sources"] if s.get("source_name") != parsed["source_name"]]
        notebook["sources"].append(source_entry)
        notebook["updated_at"] = int(time.time())
        self._save_store()
        LOGGER.info(f"Added source '{parsed['source_name']}' to notebook {notebook_id}")
        return source_entry

    def toggle_source_active(self, notebook_id: str, source_id: str, active: bool) -> bool:
        notebook = self.get_notebook(notebook_id)
        if not notebook:
            return False
        for s in notebook.get("sources", []):
            if s.get("id") == source_id:
                s["active"] = active
                notebook["updated_at"] = int(time.time())
                self._save_store()
                return True
        return False

    def delete_notebook(self, notebook_id: str) -> bool:
        if notebook_id in self.data:
            del self.data[notebook_id]
            self._save_store()
            LOGGER.info(f"Deleted notebook {notebook_id}")
            return True
        return False
