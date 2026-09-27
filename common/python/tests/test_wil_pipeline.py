import pytest
import asyncio
from wil.pipeline import WILPipeline

@pytest.mark.asyncio
async def test_pipeline_online_check():
    # If SearXNG is not running yet, check_searxng_online should return False
    pipeline = WILPipeline()
    online = await pipeline.check_searxng_online()
    # Should not crash
    assert isinstance(online, bool)

@pytest.mark.asyncio
async def test_pipeline_offline_fallback():
    pipeline = WILPipeline(base_url="http://localhost:9999") # non-existent port
    
    # We will capture chunks
    chunks = []
    def on_chunk(c):
        chunks.append(c)
        
    res = await pipeline.run("What is Bitcoin?", on_chunk=on_chunk)
    assert res["needs_web_search"] is True
    assert res["searxng_offline"] is True
    assert len(chunks) > 0


def test_append_clickable_sources_replaces_plain_source_section():
    pipeline = WILPipeline()
    response = "\n".join([
        "Top picks include useful options [1].",
        "",
        "Sources:",
        "Amazon.in: Gaming Mice Under 1000",
        "EliteHubs: Gaming Mouse Under Rs.1,000",
    ])
    sources = [
        {"title": "Amazon.in: Gaming Mice Under 1000", "url": "https://amazon.in/example"},
        {"title": "EliteHubs: Gaming Mouse Under Rs.1,000", "url": "https://elitehubs.com/example"},
    ]

    formatted = pipeline.append_clickable_sources(response, sources)

    assert "Amazon.in: Gaming Mice Under 1000\n" not in formatted
    assert "- [Amazon.in: Gaming Mice Under 1000](https://amazon.in/example)" in formatted
    assert "- [EliteHubs: Gaming Mouse Under Rs.1,000](https://elitehubs.com/example)" in formatted
