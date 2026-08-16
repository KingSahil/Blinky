"""
Recipe registry — stores learned knowledge (not step sequences).
Recipes inject contextual guidance into the LLM prompt rather than
blindly replaying old steps.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

LOGGER = logging.getLogger("blinky.computer_use.recipes")

RECIPE_SCHEMA_VERSION = 2
REGISTRY_INDEX_FILE = "registry.json"
GC_INTERVAL = 50
STALE_AGE_DAYS = 7
LOCK_TIMEOUT = 1.0
CONFIDENCE_THRESHOLD = 0.3


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _acquire_lock_fd(fd: Any, timeout: float = LOCK_TIMEOUT) -> Any | None:
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except (IOError, OSError):
                time.sleep(0.05)
        return None
    except OSError:
        return None


class RecipeRegistry:
    """Stores learned knowledge per intent/app, injects into LLM context."""

    def __init__(self, recipes_dir: str):
        self._recipes_dir = recipes_dir
        self._index: dict[str, dict[str, Any]] = {}
        self._lookup_count = 0
        if not os.path.isdir(recipes_dir):
            os.makedirs(recipes_dir, exist_ok=True)
        self._load_index()

    # ── file paths ──────────────────────────────────────────────

    def _index_path(self) -> str:
        return os.path.join(self._recipes_dir, REGISTRY_INDEX_FILE)

    def _recipe_path(self, recipe_id: str) -> str:
        return os.path.join(self._recipes_dir, f"{recipe_id}.json")

    # ── index persistence ───────────────────────────────────────

    def _load_index(self) -> None:
        path = self._index_path()
        if not os.path.exists(path):
            self._index = {}
            self._persist_index()
            LOGGER.info("Initialized empty recipe registry at %s", self._recipes_dir)
            return
        try:
            with open(path) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("index not a dict")
            valid: dict[str, dict[str, Any]] = {}
            for rid, entry in data.items():
                recipe_file = self._recipe_path(rid)
                if not os.path.exists(recipe_file):
                    continue
                if isinstance(entry, dict) and "intent" in entry:
                    # Reconcile status from the recipe file itself (the Tauri
                    # command may have activated/discarded it out-of-band).
                    try:
                        with open(recipe_file) as rf:
                            recipe = json.load(rf)
                        if recipe.get("status") == "active":
                            entry.pop("status", None)
                        elif recipe.get("status") == "pending":
                            entry["status"] = "pending"
                        else:
                            entry.pop("status", None)
                    except (json.JSONDecodeError, OSError):
                        pass
                    valid[rid] = entry
            self._index = valid
        except (json.JSONDecodeError, OSError, ValueError) as e:
            LOGGER.warning("Corrupt recipe index, resetting: %s", e)
            self._index = {}
        self._persist_index()
        self._gc()

    def _persist_index(self) -> None:
        try:
            with open(self._index_path(), "w") as f:
                lock = _acquire_lock_fd(f)
                if lock is not None:
                    json.dump(self._index, f, indent=2)
                    fcntl.flock(lock, fcntl.LOCK_UN)
        except OSError as e:
            LOGGER.warning("Failed to write index: %s", e)

    # ── knowledge extraction ────────────────────────────────────

    def _extract_workflow(self, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sanitized goal-path: only steps that succeeded, in order, deduped.

        Filters out failed attempts, repeated same-tool loops (keeps the last
        successful occurrence), and screenshot-only probes that didn't lead to
        an action. The result is the *minimal action sequence* that worked —
        exactly what a future task should take *inspiration* from, never
        blindly replay.
        """
        workflow: list[dict[str, Any]] = []
        for s in steps:
            if not s.get("success"):
                continue
            tool = s.get("tool", "")
            if not tool:
                continue
            args = s.get("args") or {}

            # Skip pure inspection probes that produced no action
            if tool == "screenshot" and not args:
                continue

            # Dedupe: if the previous kept step is the same tool+args, skip
            if workflow and workflow[-1].get("tool") == tool:
                prev_args = workflow[-1].get("args") or {}
                if prev_args == args:
                    continue

            entry: dict[str, Any] = {"tool": tool}
            if args:
                entry["args"] = args
            if s.get("message"):
                entry["message"] = str(s["message"])[:200]
            workflow.append(entry)

        # Drop trailing verification screenshots (they confirm, not act)
        if workflow and workflow[-1].get("tool") == "screenshot":
            workflow = workflow[:-1]
        return workflow

    # ── pending save (user-confirmed) ───────────────────────────

    def save_pending(
        self, query: str, steps: list[dict[str, Any]], answer: str
    ) -> dict[str, Any] | None:
        """Build a recipe but stage it as PENDING — the user confirms before
        it enters the active registry.

        Returns {"recipe_id", "preview"} so the UI can ask "Save this
        workflow?" with a human-readable summary.
        """
        knowledge = self._extract_knowledge(query, steps, answer)
        workflow = self._extract_workflow(steps)
        if not knowledge and not workflow:
            return None

        rid = str(uuid.uuid4())
        intent = self._extract_intent(query)
        app_patterns = self._extract_app_patterns(query, steps)

        recipe = {
            "id": rid,
            "schema_version": RECIPE_SCHEMA_VERSION,
            "intent": intent,
            "app_patterns": app_patterns,
            "knowledge": knowledge,
            "workflow": workflow,
            "original_query": query,
            "status": "pending",
            "successes": 0,
            "failures": 0,
            "created_at": _utc_iso(),
            "last_used_at": _utc_iso(),
        }

        try:
            with open(self._recipe_path(rid), "w") as f:
                lock = _acquire_lock_fd(f)
                if lock is not None:
                    json.dump(recipe, f, indent=2)
                    fcntl.flock(lock, fcntl.LOCK_UN)
        except OSError as e:
            LOGGER.warning("Failed to stage pending recipe: %s", e)
            return None

        # Pending recipes are tracked in the index so they can be confirmed
        self._index[rid] = {
            "intent": intent,
            "app_patterns": app_patterns,
            "successes": 0,
            "failures": 0,
            "status": "pending",
        }
        self._persist_index()

        preview = [
            f"{step.get('tool', '')}({', '.join(f'{k}={v}' for k, v in (step.get('args') or {}).items())})"
            for step in workflow
        ]
        LOGGER.info("Staged pending recipe %s (intent=%s, %d workflow steps)",
                    rid, intent, len(workflow))
        return {"recipe_id": rid, "preview": preview, "intent": intent}

    def confirm_pending(self, recipe_id: str, save: bool) -> bool:
        """User decision on a staged recipe: activate it or discard it."""
        path = self._recipe_path(recipe_id)
        if not os.path.exists(path):
            return False
        try:
            with open(path) as f:
                recipe = json.load(f)
        except (json.JSONDecodeError, OSError):
            return False

        if not save:
            try:
                os.remove(path)
            except OSError:
                pass
            self._index.pop(recipe_id, None)
            self._persist_index()
            LOGGER.info("Discarded pending recipe %s", recipe_id)
            return True

        recipe["status"] = "active"
        recipe["successes"] = 1
        try:
            with open(path, "w") as f:
                lock = _acquire_lock_fd(f)
                if lock is not None:
                    json.dump(recipe, f, indent=2)
                    fcntl.flock(lock, fcntl.LOCK_UN)
        except OSError as e:
            LOGGER.warning("Failed to activate recipe %s: %s", recipe_id, e)
            return False

        if recipe_id in self._index:
            self._index[recipe_id]["successes"] = 1
            self._index[recipe_id].pop("status", None)
        self._persist_index()
        LOGGER.info("Activated recipe %s", recipe_id)
        return True

    def _extract_knowledge(
        self, query: str, steps: list[dict[str, Any]], answer: str
    ) -> list[str]:
        """Derive factual knowledge snippets from a successful interaction."""
        knowledge: list[str] = []

        # App discovery facts
        for s in steps:
            if s.get("tool") == "open_app" and s.get("success"):
                app = s.get("args", {}).get("app_name", "")
                msg = s.get("message", "")
                if "binary:" in msg:
                    binary = msg.split("binary:")[-1].strip().rstrip(").")
                    knowledge.append(f"Launch '{app}' with binary: {binary}")
                elif app:
                    knowledge.append(f"'{app}' can be launched with open_app")

        # Input patterns
        if any(s.get("tool") == "type_text" and s.get("success") for s in steps):
            knowledge.append("This task accepts typed text input")
        if any(s.get("tool") == "press_key" and s.get("success") for s in steps):
            knowledge.append("Press Enter after typing to submit")

        # Verification
        if any(s.get("tool") == "screenshot" and s.get("success") for s in steps):
            knowledge.append("Screenshot can verify results visually")

        return knowledge

    def _extract_intent(self, query: str) -> str:
        q = query.lower().strip()
        patterns = [
            (r"\b(calculate|calculator|calc|compute|math|sum|add|subtract|multiply|divide)\b", "calculate"),
            (r"\b(screenshot|screen|capture)\b", "capture"),
            (r"\b(inspect|examine|analyze|state|what|show)\b", "inspect"),
            (r"\b(click|press|select|push|hit)\b", "click"),
            (r"\b(type|enter|write|input)\b", "type"),
            (r"\b(list|show|find|enumerate|windows)\b", "discover"),
            (r"\b(close|quit|exit|kill)\b", "close"),
            (r"\bopen\b", "launch"),
        ]
        for pat, intent in patterns:
            if re.search(pat, q):
                return intent
        return "generic"

    def _extract_app_patterns(self, query: str, steps: list[dict]) -> list[str]:
        patterns: set[str] = set()
        q = query.lower()
        known = ["calculator", "firefox", "chrome", "terminal", "settings",
                 "files", "dolphin", "kate", "code", "vscode", "discord", "equibop"]
        for a in known:
            if a in q:
                patterns.add(a)
        for s in steps:
            if s.get("tool") == "open_app":
                app = str(s.get("args", {}).get("app_name", "")).lower()
                if app:
                    patterns.add(app)
        return sorted(patterns)

    # ── save / match / inject ───────────────────────────────────

    def save(
        self, query: str, steps: list[dict[str, Any]], answer: str
    ) -> str | None:
        """Save learned knowledge + sanitized workflow from a successful task."""
        knowledge = self._extract_knowledge(query, steps, answer)
        workflow = self._extract_workflow(steps)
        if not knowledge and not workflow:
            return None

        rid = str(uuid.uuid4())
        intent = self._extract_intent(query)
        app_patterns = self._extract_app_patterns(query, steps)

        recipe = {
            "id": rid,
            "schema_version": RECIPE_SCHEMA_VERSION,
            "intent": intent,
            "app_patterns": app_patterns,
            "knowledge": knowledge,
            "workflow": workflow,
            "original_query": query,
            "successes": 1,
            "failures": 0,
            "created_at": _utc_iso(),
            "last_used_at": _utc_iso(),
        }

        try:
            with open(self._recipe_path(rid), "w") as f:
                lock = _acquire_lock_fd(f)
                json.dump(recipe, f, indent=2)
                if lock is not None:
                    fcntl.flock(lock, fcntl.LOCK_UN)
        except OSError as e:
            LOGGER.warning("Failed to save recipe: %s", e)
            return None

        self._index[rid] = {
            "intent": intent,
            "app_patterns": app_patterns,
            "successes": 1,
            "failures": 0,
        }
        self._persist_index()

        LOGGER.info("Saved recipe %s: intent=%s, patterns=%s, knowledge=%d",
                     rid, intent, app_patterns, len(knowledge))
        return rid

    def match_query(self, query: str, limit: int = 3) -> list[tuple[str, float]]:
        """Return matching recipe IDs with confidence scores (best first).

        Scoring combines:
        - app-pattern overlap (existing)
        - intent agreement (query verb hints vs recipe intent)
        - success ratio (recipes that worked more get a small boost)
        """
        self._lookup_count += 1
        if self._lookup_count % GC_INTERVAL == 0:
            self._gc()

        q = query.lower().strip()
        if not q:
            return []

        q_words = set(re.findall(r"[a-zA-Z0-9.+/]+", q))
        if not q_words:
            return []

        query_intent = self._extract_intent(query)
        scores: list[tuple[str, float]] = []
        for rid, entry in list(self._index.items()):
            # Skip staged-but-unconfirmed recipes — only active ones inspire.
            if entry.get("status") == "pending":
                continue
            patterns: list[str] = entry.get("app_patterns", [])
            overlap = sum(1 for p in patterns if p in q)
            word_hits = sum(1 for w in q_words for p in patterns if p in w or w in p)

            base = max(
                min(overlap / max(len(patterns), 1), 1.0),
                min(word_hits / max(len(q_words), 1), 1.0),
            )

            # Intent agreement: same verb family → meaningful boost
            intent = entry.get("intent", "")
            if intent and query_intent == intent:
                base = min(base + 0.15, 1.0)

            succ = entry.get("successes", 0)
            fail = entry.get("failures", 0)
            total = succ + fail
            ratio = succ / total if total > 0 else 0.5
            combined = base * (0.4 + 0.6 * ratio)

            if combined > CONFIDENCE_THRESHOLD:
                scores.append((rid, round(combined, 3)))

        scores.sort(key=lambda x: -x[1])
        if scores:
            LOGGER.info("Recipe match: %d candidates, best=%.3f", len(scores), scores[0][1])
        return scores[:limit]

    def get_context(self, recipe_id: str) -> str | None:
        """Return a structured context block to inject into the LLM prompt.

        Format (numbered workflow + facts) is designed for *inspiration*:
        the LLM sees what worked before for a similar goal, in order, with an
        explicit instruction not to replay blindly. The workflow is the
        sanitized goal-path (success steps only), so failed detours never
        leak into the recommendation.
        """
        path = self._recipe_path(recipe_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                recipe = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        # Update last_used_at
        recipe["last_used_at"] = _utc_iso()
        try:
            with open(path, "w") as f:
                json.dump(recipe, f, indent=2)
        except OSError:
            pass

        parts: list[str] = ["Previous experience with a similar goal (use as INSPIRATION only — do not blindly replay; verify each step against the current screen):"]
        intent = recipe.get("intent", "")
        if intent:
            parts.append(f"- Goal type: {intent}")
        if recipe.get("app_patterns"):
            parts.append(f"- Related apps: {', '.join(recipe['app_patterns'][:5])}")

        workflow: list[dict[str, Any]] = recipe.get("workflow", [])
        if workflow:
            parts.append("- A previously successful sequence:")
            for i, step in enumerate(workflow, 1):
                tool = step.get("tool", "")
                args = step.get("args") or {}
                arg_str = ", ".join(f"{k}={v}" for k, v in list(args.items())[:3])
                note = f"  ({step.get('message', '')})" if step.get("message") and len(str(step.get("message", ""))) < 80 else ""
                parts.append(f"  {i}. {tool}({arg_str}){note}")
        else:
            parts.append("- (no reusable step sequence recorded)")

        knowledge: list[str] = recipe.get("knowledge", [])
        if knowledge:
            parts.append("- Facts:")
            parts.extend(f"  - {k}" for k in knowledge[:5])

        succ = int(recipe.get("successes", 0))
        fail = int(recipe.get("failures", 0))
        total = succ + fail
        if total > 0:
            parts.append(f"- Track record: {succ} success(es), {fail} failure(s)")

        return "\n" + "\n".join(parts) + "\n"

    def decay(self, recipe_id: str, success: bool) -> None:
        """Adjust confidence after a task using this recipe's knowledge."""
        path = self._recipe_path(recipe_id)
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                recipe = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        if success:
            recipe["successes"] = recipe.get("successes", 0) + 1
        else:
            recipe["failures"] = recipe.get("failures", 0) + 1
        recipe["last_used_at"] = _utc_iso()

        try:
            with open(path, "w") as f:
                lock = _acquire_lock_fd(f)
                json.dump(recipe, f, indent=2)
                if lock is not None:
                    fcntl.flock(lock, fcntl.LOCK_UN)
        except OSError:
            return

        self._index[recipe_id]["successes"] = recipe["successes"]
        self._index[recipe_id]["failures"] = recipe["failures"]
        self._persist_index()

        succ = recipe["successes"]
        fail = recipe["failures"]
        LOGGER.info("Recipe %s: successes=%d failures=%d rate=%.2f",
                     recipe_id, succ, fail, succ / max(succ + fail, 1))

        if fail > succ and succ == 0:
            self._evict(recipe_id)

    def _evict(self, recipe_id: str) -> None:
        path = self._recipe_path(recipe_id)
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
        self._index.pop(recipe_id, None)
        self._persist_index()

    def _gc(self) -> None:
        evict: list[str] = []
        for rid, entry in list(self._index.items()):
            if entry.get("failures", 0) <= entry.get("successes", 0):
                continue
            path = self._recipe_path(rid)
            if not os.path.exists(path):
                evict.append(rid)
                continue
            try:
                with open(path) as f:
                    r = json.load(f)
                created = datetime.fromisoformat(r.get("created_at", ""))
                if (datetime.now(timezone.utc) - created).days >= STALE_AGE_DAYS:
                    evict.append(rid)
            except Exception:
                evict.append(rid)
        for rid in evict:
            self._evict(rid)
        if evict:
            LOGGER.info("GC evicted %d stale recipes", len(evict))
