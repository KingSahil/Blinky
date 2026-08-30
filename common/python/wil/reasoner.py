import os
import json
import logging
import requests
from typing import Dict, Any, List, Callable
from utils.location import get_user_location

LOGGER = logging.getLogger("blinky.reasoner")

class Reasoner:
    def synthesize(self, query: str, context: str, callback: Callable[[str], None]) -> str:
        provider = (os.getenv("BLINKY_AI_PROVIDER", "ollama").strip() or "ollama").lower()
        location_info = get_user_location()
        user_loc_str = location_info.get("display") or "Unknown"
        
        prompt = f"""
You are Blinky, a helpful AI assistant.
User's approximate location: {user_loc_str}
The user asked: "{query}"

We searched the web and gathered this information:
{context}

Synthesize a comprehensive, professional, user-friendly response directly answering the user's request.
If the user asks for local recommendations (e.g. restaurants, shops, services, weather near them), use the retrieved information and their location ({user_loc_str}) to provide specific places, ratings, descriptions, addresses/areas, and details.
Incorporate citations or references to the sources when appropriate.
Avoid mentioning system internal details (like "Playwright script output", "retrieved HTML", "SearXNG"). Give direct details.
"""
        full_response = []
        
        def handle_chunk(chunk: str):
            full_response.append(chunk)
            callback(chunk)

        if provider == "groq" or (os.getenv("GROQ_API_KEY") and provider != "ollama"):
            api_key = os.getenv("GROQ_API_KEY", "").strip()
            model = os.getenv("BLINKY_GROQ_MODEL", "openai/gpt-oss-120b").strip() or "openai/gpt-oss-120b"
            if model in ("llama-3.3-70b-versatile", "llama-3.2-90b-vision-preview", "llama-3.2-11b-vision-preview"):
                model = "openai/gpt-oss-120b"
            groq_url = os.getenv("BLINKY_GROQ_URL", "https://api.groq.com/openai/v1/chat/completions").strip()

            try:
                response = requests.post(
                    groq_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "temperature": 0.3,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": True
                    },
                    stream=True,
                    timeout=30
                )
                response.raise_for_status()
                for chunk in response.iter_lines():
                    if chunk:
                        line = chunk.decode("utf-8").strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                delta = data["choices"][0]["delta"].get("content", "")
                                if delta:
                                    handle_chunk(delta)
                            except Exception:
                                pass
            except Exception as e:
                LOGGER.error(f"Groq synthesis failed: {e}")
                handle_chunk(f"\n[Synthesis Error: {str(e)}]")
        else:
            # Try ask_text_model from ai.client which respects BLINKY_AI_PROVIDER (mimo, deepseek, ollama, custom)
            try:
                from ai.client import ask_text_model
                res = ask_text_model(prompt, max_tokens=1024)
                text = ""
                if isinstance(res, dict):
                    text = res.get("summary") or res.get("response") or res.get("answer") or ""
                elif isinstance(res, str):
                    text = res
                if text:
                    handle_chunk(text)
            except Exception as exc:
                LOGGER.error(f"Synthesis failed via ask_text_model: {exc}")
                # Fallback to direct Ollama attempt
                ollama_url = os.getenv("BLINKY_OLLAMA_URL", "http://localhost:11434/api/generate").strip()
                model = os.getenv("BLINKY_OLLAMA_MODEL", "gemma4:e4b").strip()
                try:
                    response = requests.post(
                        ollama_url,
                        json={
                            "model": model,
                            "prompt": prompt,
                            "stream": True,
                            "options": {
                                "temperature": 0.3
                            }
                        },
                        stream=True,
                        timeout=45
                    )
                    response.raise_for_status()
                    for chunk in response.iter_lines():
                        if chunk:
                            try:
                                data = json.loads(chunk.decode("utf-8"))
                                delta = data.get("response", "")
                                if delta:
                                    handle_chunk(delta)
                            except Exception:
                                pass
                except Exception as e:
                    LOGGER.error(f"Ollama synthesis failed: {e}")
                    handle_chunk(f"\n[Synthesis Error: {str(e)}]")
                
        return "".join(full_response)
