import pytest
import asyncio
from wil.searxng_client import SearXNGClient

@pytest.mark.asyncio
async def test_searxng_client_init():
    client = SearXNGClient()
    assert client.base_url == "http://localhost:8888"

@pytest.mark.asyncio
async def test_searxng_client_headers():
    client = SearXNGClient()
    headers = client._get_headers()
    assert "User-Agent" in headers
    assert headers["Accept"] == "application/json"
