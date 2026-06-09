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
