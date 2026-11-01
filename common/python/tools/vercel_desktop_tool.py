"""Registered accessibility desktop backend shared by PC and mobile."""
from __future__ import annotations
import json
import sys
import time


def resolve_vercel_desktop_request(question: str) -> dict | None:
    from computer_use.vercel_engine import should_route
    if should_route(question):
        return {"action": "status" if question.strip().lower() == "agent-desktop status" else "task", "task": question}
    return None


def handle_request(params: dict) -> dict:
    from computer_use.vercel_engine import invoke, run_desktop_request
    if params.get("action") == "status":
        try:
            result = invoke("agent-desktop", ["status"])
            return {"success": True, "message": "agent-desktop is available.", "data": result["data"]}
        except Exception as exc:
            return {"success": False, "message": str(exc)}
    result = run_desktop_request(params.get("task", ""), time.perf_counter(), [])
    return {**result, "message": result["summary"]}


if __name__ == "__main__":
    print(json.dumps(handle_request(json.loads(sys.argv[1]))))
