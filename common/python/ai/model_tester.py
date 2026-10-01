"""
Model Tester: 1-Token Health Check Utility
Tests API keys and model availability across Groq, Gemini, DeepSeek, Ollama, and Custom endpoints
with minimal token consumption (1 token) and returns latency & diagnostics.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional
import requests

from utils.logging import get_logger

LOGGER = get_logger("blinky.model_tester")

DEFAULT_TIMEOUT = 10.0


def ping_ai_model(
    provider: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    custom_url: Optional[str] = None,
) -> dict[str, Any]:
    """
    Sends a 1-token probe to verify model availability and key authentication.
    Returns:
        {
            "ok": bool,
            "provider": str,
            "model": str,
            "latency_ms": int,
            "status_code": int,
            "error": Optional[str],
            "details": Optional[str]
        }
    """
    prov = (provider or "groq").lower().strip()
    t_start = time.time()

    try:
        if prov == "groq":
            key = (api_key or os.getenv("GROQ_API_KEY", "")).strip()
            if not key:
                return {
                    "ok": False,
                    "provider": prov,
                    "model": model or "unknown",
                    "latency_ms": 0,
                    "status_code": 401,
                    "error": "Missing Groq API Key",
                    "details": "Please enter a valid Groq API key."
                }
            active_model = (model or os.getenv("BLINKY_GROQ_MODEL", "qwen/qwen3.8-27b")).strip() or "qwen/qwen3.8-27b"
            url = os.getenv("BLINKY_GROQ_URL", "https://api.groq.com/openai/v1/chat/completions").strip()
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": active_model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                    "temperature": 0.0,
                },
                timeout=DEFAULT_TIMEOUT,
            )
            latency = int((time.time() - t_start) * 1000)
            data = resp.json() if resp.content else {}
            if resp.status_code == 200:
                return {
                    "ok": True,
                    "provider": prov,
                    "model": active_model,
                    "latency_ms": latency,
                    "status_code": 200,
                    "error": None,
                    "details": f"Online ({latency}ms)"
                }
            else:
                err_msg = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
                return {
                    "ok": False,
                    "provider": prov,
                    "model": active_model,
                    "latency_ms": latency,
                    "status_code": resp.status_code,
                    "error": err_msg,
                    "details": f"Groq Error: {err_msg}"
                }

        elif prov == "gemini":
            key = (api_key or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")).strip()
            if not key:
                return {
                    "ok": False,
                    "provider": prov,
                    "model": model or "unknown",
                    "latency_ms": 0,
                    "status_code": 401,
                    "error": "Missing Gemini API Key",
                    "details": "Please enter a valid Google Gemini API key."
                }
            active_model = (model or "gemini-2.5-flash").strip()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{active_model}:generateContent?key={key}"
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": "ping"}]}],
                    "generationConfig": {"maxOutputTokens": 1, "temperature": 0.0},
                },
                timeout=DEFAULT_TIMEOUT,
            )
            latency = int((time.time() - t_start) * 1000)
            data = resp.json() if resp.content else {}
            if resp.status_code == 200:
                return {
                    "ok": True,
                    "provider": prov,
                    "model": active_model,
                    "latency_ms": latency,
                    "status_code": 200,
                    "error": None,
                    "details": f"Online ({latency}ms)"
                }
            else:
                err_msg = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
                return {
                    "ok": False,
                    "provider": prov,
                    "model": active_model,
                    "latency_ms": latency,
                    "status_code": resp.status_code,
                    "error": err_msg,
                    "details": f"Gemini Error: {err_msg}"
                }

        elif prov == "deepseek":
            key = (api_key or os.getenv("DEEPSEEK_API_KEY", "")).strip()
            if not key:
                return {
                    "ok": False,
                    "provider": prov,
                    "model": model or "unknown",
                    "latency_ms": 0,
                    "status_code": 401,
                    "error": "Missing DeepSeek API Key",
                    "details": "Please enter a valid DeepSeek API key."
                }
            active_model = (model or "deepseek-chat").strip()
            url = "https://api.deepseek.com/chat/completions"
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": active_model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                timeout=DEFAULT_TIMEOUT,
            )
            latency = int((time.time() - t_start) * 1000)
            data = resp.json() if resp.content else {}
            if resp.status_code == 200:
                return {
                    "ok": True,
                    "provider": prov,
                    "model": active_model,
                    "latency_ms": latency,
                    "status_code": 200,
                    "error": None,
                    "details": f"Online ({latency}ms)"
                }
            else:
                err_msg = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
                return {
                    "ok": False,
                    "provider": prov,
                    "model": active_model,
                    "latency_ms": latency,
                    "status_code": resp.status_code,
                    "error": err_msg,
                    "details": f"DeepSeek Error: {err_msg}"
                }

        elif prov == "ollama":
            base_url = (custom_url or os.getenv("BLINKY_OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
            active_model = (model or os.getenv("BLINKY_OLLAMA_MODEL", "qwen2.5:7b")).strip()
            url = f"{base_url}/api/generate"
            resp = requests.post(
                url,
                json={"model": active_model, "prompt": "ping", "stream": False},
                timeout=DEFAULT_TIMEOUT,
            )
            latency = int((time.time() - t_start) * 1000)
            if resp.status_code == 200:
                return {
                    "ok": True,
                    "provider": prov,
                    "model": active_model,
                    "latency_ms": latency,
                    "status_code": 200,
                    "error": None,
                    "details": f"Online ({latency}ms)"
                }
            else:
                return {
                    "ok": False,
                    "provider": prov,
                    "model": active_model,
                    "latency_ms": latency,
                    "status_code": resp.status_code,
                    "error": f"Ollama HTTP {resp.status_code}",
                    "details": resp.text[:200]
                }

        elif prov in ("custom", "openai"):
            key = (api_key or os.getenv("CUSTOM_API_KEY", "")).strip()
            base_url = (custom_url or os.getenv("BLINKY_CUSTOM_URL", "")).rstrip("/")
            if not base_url:
                return {
                    "ok": False,
                    "provider": prov,
                    "model": model or "unknown",
                    "latency_ms": 0,
                    "status_code": 400,
                    "error": "Missing Custom API URL",
                    "details": "Please enter custom OpenAI-compatible endpoint URL."
                }
            endpoint = f"{base_url}/chat/completions" if not base_url.endswith("/chat/completions") else base_url
            active_model = (model or os.getenv("BLINKY_CUSTOM_MODEL", "default")).strip()
            headers = {"Content-Type": "application/json"}
            if key:
                headers["Authorization"] = f"Bearer {key}"
            resp = requests.post(
                endpoint,
                headers=headers,
                json={
                    "model": active_model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                timeout=DEFAULT_TIMEOUT,
            )
            latency = int((time.time() - t_start) * 1000)
            if resp.status_code == 200:
                return {
                    "ok": True,
                    "provider": prov,
                    "model": active_model,
                    "latency_ms": latency,
                    "status_code": 200,
                    "error": None,
                    "details": f"Online ({latency}ms)"
                }
            else:
                return {
                    "ok": False,
                    "provider": prov,
                    "model": active_model,
                    "latency_ms": latency,
                    "status_code": resp.status_code,
                    "error": f"Custom Endpoint HTTP {resp.status_code}",
                    "details": resp.text[:200]
                }

        else:
            return {
                "ok": False,
                "provider": prov,
                "model": model or "unknown",
                "latency_ms": 0,
                "status_code": 400,
                "error": f"Unsupported provider: {provider}",
                "details": "Supported: groq, gemini, deepseek, ollama, custom"
            }

    except Exception as exc:
        latency = int((time.time() - t_start) * 1000)
        LOGGER.warning("Ping failed for %s (%s): %s", prov, model, exc)
        return {
            "ok": False,
            "provider": prov,
            "model": model or "unknown",
            "latency_ms": latency,
            "status_code": 0,
            "error": str(exc),
            "details": f"Connection error: {exc}"
        }
