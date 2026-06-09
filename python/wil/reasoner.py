import os
import json
import logging
import requests
from typing import Dict, Any, List, Callable

LOGGER = logging.getLogger("blinky.reasoner")

class Reasoner:
    def synthesize(self, query: str, context: str, callback: Callable[[str], None]) -> str:
        provider = (os.getenv("BLINKY_AI_PROVIDER", "ollama").strip() or "ollama").lower()
        
        prompt = f"""
You are Blinky, a helpful AI assistant.
The user asked: "{query}"

We searched the web and gathered this information:
{context}

Synthesize a comprehensive, professional, user-friendly response directly answering the user's request.
Incorporate citations or references to the sources when appropriate.
Avoid mentioning system internal details (like "Playwright script output", "retrieved HTML", "SearXNG"). Give direct details.
"""
        full_response = []
        
        def handle_chunk(chunk: str):
            full_response.append(chunk)
            callback(chunk)

        if provider == "groq":
            api_key = os.getenv("GROQ_API_KEY", "").strip()
            model = os.getenv("BLINKY_GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct").strip()
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
            # Ollama
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
