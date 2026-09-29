from __future__ import annotations

from typing import Dict, Any, List, Optional


def build_okf_prompt_context(
    notebook: Dict[str, Any],
    query: str,
    vector_matches: Optional[List[Tuple[Dict[str, Any], float]]] = None
) -> Dict[str, str]:
    """
    Assembles active notebook document sources or top-K vector search chunks into a grounded LLM prompt system payload.
    """
    sources = notebook.get("sources", [])
    active_sources = [s for s in sources if s.get("active", True)]

    if vector_matches:
        v_blocks = []
        for match, score in vector_matches:
            src_name = match.get("source_name", "unknown")
            idx = match.get("chunk_index", 0)
            content = match.get("content", "")
            v_blocks.append(
                f"### VECTOR CHUNK: {src_name} (Part {idx + 1}, Match Score: {int(score * 100)}%)\n{content}"
            )
        sources_payload = "\n\n".join(v_blocks)
    else:
        okf_source_blocks = []
        for src in active_sources:
            okf_source_blocks.append(src.get("okf_content", ""))
        sources_payload = "\n\n".join(okf_source_blocks) if okf_source_blocks else "[No active notebook sources selected]"

    system_prompt = (
        "You are Blinky Notebook AI, a grounded research tutor and document intelligence assistant.\n"
        "You answer user queries strictly using the provided Notebook Document Sources.\n\n"
        "RULES:\n"
        "1. Every factual statement or summary MUST be grounded directly in the provided sources.\n"
        "2. Cite your sources using exact inline badges: [Source: filename.pdf] or [Source: filename.md].\n"
        "3. If a question cannot be answered from the provided sources, explicitly state what information is missing.\n"
        "4. Keep your formatting clean using Markdown headers, bullet points, and code blocks.\n"
    )

    user_prompt = (
        f"--- GROUNDED NOTEBOOK SOURCES ---\n"
        f"{sources_payload}\n\n"
        f"--- USER QUERY ---\n"
        f"{query.strip()}"
    )

    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "source_count": len(vector_matches) if vector_matches else len(active_sources),
    }
