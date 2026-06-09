import logging
import re
from typing import List, Dict, Any

LOGGER = logging.getLogger("blinky.processor")

class ContentProcessor:
    def __init__(self, char_budget: int = 15000):
        self.char_budget = char_budget

    def clean_text(self, text: str) -> str:
        # Remove excessive whitespace/newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def process(self, query: str, acquired_contents: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Merge all contents and extract relevant sentences/paragraphs
        processed_sources = []
        combined_text_parts = []
        
        current_size = 0
        
        for idx, item in enumerate(acquired_contents):
            url = item.get("url")
            title = item.get("title", f"Source {idx}")
            text = self.clean_text(item.get("text", ""))
            
            if not text:
                continue
                
            # If the single page exceeds our budget, we truncate it or slice it.
            # To be smart, we can extract paragraphs containing keywords from the query.
            keywords = [k.lower() for k in query.split() if len(k) > 3]
            paragraphs = text.split("\n\n")
            
            selected_paragraphs = []
            for p in paragraphs:
                p_clean = p.strip()
                if not p_clean:
                    continue
                # Score paragraph by keyword match
                score = sum(1 for kw in keywords if kw in p_clean.lower())
                selected_paragraphs.append((score, p_clean))
                
            # Sort paragraphs by relevance score
            selected_paragraphs.sort(key=lambda x: x[0], reverse=True)
            
            # Reconstruct text from top paragraphs up to a budget per source
            source_text_parts = []
            source_budget = self.char_budget // len(acquired_contents)
            source_size = 0
            
            for score, p in selected_paragraphs:
                if source_size + len(p) < source_budget:
                    source_text_parts.append(p)
                    source_size += len(p)
                elif not source_text_parts:
                    # Keep at least the top paragraph
                    source_text_parts.append(p[:source_budget])
                    break
                    
            source_text = "\n\n".join(source_text_parts)
            
            processed_sources.append({
                "url": url,
                "title": title,
                "text": source_text
            })
            
            combined_text_parts.append(f"Source: {title} ({url})\nContent:\n{source_text}\n---")
            
        final_context = "\n\n".join(combined_text_parts)
        
        # Sufficiency check: do we have enough content?
        is_sufficient = len(final_context) > 200
        
        return {
            "context": final_context,
            "sources": processed_sources,
            "is_sufficient": is_sufficient,
            "length": len(final_context)
        }
