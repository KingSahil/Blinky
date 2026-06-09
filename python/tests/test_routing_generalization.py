import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
import shutil

import agent_router
from utils.generalizer import generalize_tool, read_registry_safe, write_registry_safe

@pytest.fixture
def temp_registry(tmp_path):
    registry_file = tmp_path / "registry.json"
    registry_file.write_text(json.dumps({}))
    return registry_file

@pytest.mark.asyncio
async def test_route_cache():
    # Test that route cache is checked and returns cached decisions
    agent_router.ROUTE_CACHE.clear()
    agent_router.ROUTE_CACHE["test query"] = {
        "match": True,
        "tool_name": "test_tool",
        "confidence": 90,
        "reasoning": "cached",
        "arguments": {"key": "val"}
    }

    with patch("agent_router.ask_text_model") as mock_ask:
        with patch("agent_router.load_registry_async", return_value={"test_tool": {}}):
            with patch("agent_router.execute_script", return_value=(True, {"result": "ok"}, "")) as mock_exec:
                with patch("utils.sufficiency_checker.check_sufficiency", return_value=(True, "sufficient")):
                    # We mock send_response to check if it does indeed route and run
                    with patch("agent_router.send_response") as mock_send:
                        line = json.dumps({"requestId": "123", "query": "test query"})
                        await agent_router.handle_request(line)
                        
                        # Ensure ask_text_model was NOT called because it was cached
                        mock_ask.assert_not_called()
                        # Ensure mock_exec was called with correct args
                        mock_exec.assert_called_once()
                        # Check that processing status logs show "Routing to 1 tool call(s)"
                        mock_send.assert_any_call("123", "processing", data={
                            "message": "Routing to 1 tool call(s) (Confidence: 90%)...",
                            "confidence": 90,
                            "reasoning": "cached"
                        })

@pytest.mark.asyncio
async def test_confidence_routing_threshold():
    # Test that confidence scores below 80 fall back to code generation
    agent_router.ROUTE_CACHE.clear()
    
    routing_decision = {
        "match": True,
        "tool_name": "test_tool",
        "confidence": 75, # Below 80!
        "reasoning": "low confidence matching",
        "arguments": {"key": "val"}
    }

    with patch("agent_router.ask_text_model", return_value=routing_decision) as mock_ask:
        with patch("agent_router.load_registry_async", return_value={"test_tool": {}}):
            with patch("agent_router.send_response") as mock_send:
                # We will stop/mock early in generation block to avoid actual API call
                with patch("agent_router.requests.post") as mock_post:
                    # Mock response to throw exception or return mock content to terminate handles
                    mock_post.side_effect = Exception("Stop execution in generation phase")
                    
                    line = json.dumps({"requestId": "123", "query": "low conf query"})
                    await agent_router.handle_request(line)
                    
                    # Ensure it logged that it is generating custom script due to low confidence
                    mock_send.assert_any_call("123", "processing", data={
                        "message": "No confident match (Confidence: 75%). Generating custom script...",
                        "confidence": 75,
                        "reasoning": "low confidence matching"
                    })

@pytest.mark.asyncio
async def test_generalization_loop_success(tmp_path):
    # Setup temporary directory and registry
    registry_path = tmp_path / "registry.json"
    original_tool_path = tmp_path / "lookup_mandela_info.py"
    
    # Original registry entry
    registry_data = {
        "lookup_mandela_info": {
            "name": "lookup_mandela_info",
            "description": "Lookup Nelson Mandela info on Wikipedia",
            "filepath": str(original_tool_path),
            "arguments": ["query"]
        }
    }
    registry_path.write_text(json.dumps(registry_data))
    original_tool_path.write_text("print('nelson mandela')")

    # LLM decision to generalize
    llm_decision = {
        "can_generalize": True,
        "generalized_name": "lookup_wikipedia_person",
        "description": "Lookup any person on Wikipedia",
        "arguments": ["person_name"],
        "test_arguments": {
            "person_name": "Albert Einstein"
        },
        "code": "import json\nimport sys\nprint(json.dumps({'status': 'ok'}))"
    }

    # Mock audit function
    mock_audit = MagicMock(return_value=(True, "Safe"))

    with patch("utils.generalizer.ask_text_model", return_value=llm_decision):
        # Run generalization tool
        await generalize_tool(
            "lookup_mandela_info",
            "Nelson Mandela",
            ["query"],
            registry_path,
            mock_audit
        )
        
        # Verify the original tool file is deleted and registry updated
        assert not original_tool_path.exists()
        
        updated_registry = json.loads(registry_path.read_text())
        assert "lookup_wikipedia_person" in updated_registry
        assert "lookup_mandela_info" not in updated_registry
        assert updated_registry["lookup_wikipedia_person"]["arguments"] == ["person_name"]
        
        # Verify the new generalized file exists
        gen_filepath = tmp_path / "lookup_wikipedia_person.py"
        assert gen_filepath.exists()
        assert "Albert Einstein" in gen_filepath.read_text() or "import json" in gen_filepath.read_text()

@pytest.mark.asyncio
async def test_multi_tool_concurrent_execution():
    # Test concurrent routing with multiple tool calls
    agent_router.ROUTE_CACHE.clear()
    agent_router.ROUTE_CACHE["multi query"] = {
        "match": True,
        "tool_calls": [
            {"tool_name": "lookup_youtube_stats", "arguments": {"channel_name": "@MrBeast"}},
            {"tool_name": "lookup_youtube_stats", "arguments": {"channel_name": "@PewDiePie"}}
        ],
        "confidence": 95,
        "reasoning": "two lookup requests"
    }

    mock_registry = {
        "lookup_youtube_stats": {
            "name": "lookup_youtube_stats",
            "description": "YouTube stats details",
            "arguments": ["channel_name"]
        }
    }

    with patch("agent_router.load_registry_async", return_value=mock_registry):
        with patch("agent_router.execute_script", return_value=(True, {"subscribers": "100M"}, "")) as mock_exec:
            with patch("utils.sufficiency_checker.check_sufficiency", return_value=(True, "sufficient")):
                with patch("agent_router.send_response") as mock_send:
                    line = json.dumps({"requestId": "456", "query": "multi query"})
                    await agent_router.handle_request(line)
                    
                    # Ensure execute_script was called twice (concurrently)
                    assert mock_exec.call_count == 2
                    mock_send.assert_any_call("456", "processing", data={
                        "message": "Routing to 2 tool call(s) (Confidence: 95%)...",
                        "confidence": 95,
                        "reasoning": "two lookup requests"
                    })

@pytest.mark.asyncio
async def test_sufficiency_check_fallback_triggers_generation():
    # Test that when check_sufficiency fails, it falls back to code generation
    agent_router.ROUTE_CACHE.clear()
    agent_router.ROUTE_CACHE["insufficient query"] = {
        "match": True,
        "tool_calls": [
            {"tool_name": "lookup_youtube_stats", "arguments": {"channel_name": "@MrBeast"}}
        ],
        "confidence": 90,
        "reasoning": "one lookup request"
    }

    mock_registry = {
        "lookup_youtube_stats": {
            "name": "lookup_youtube_stats",
            "description": "YouTube stats details",
            "arguments": ["channel_name"]
        }
    }

    # Custom generated tool return structure
    mock_gen_response = """
TOOL_NAME: lookup_custom_details
DESCRIPTION: Custom generated search
ARGUMENTS: query
CODE:
```python
import sys
import json
print(json.dumps({"custom_result": "done"}))
```
"""

    with patch("agent_router.load_registry_async", return_value=mock_registry):
        with patch("agent_router.execute_script") as mock_exec:
            # First tool execution returns result, second fallback execution returns success
            mock_exec.side_effect = [
                (True, {"subscribers": "N/A"}, ""), # tool output
                (True, {"custom_result": "done"}, "") # fallback tool validation run
            ]
            # Fast heuristic check passes, LLM sufficiency returns False
            with patch("utils.sufficiency_checker.check_sufficiency", return_value=(False, "Missing subscribers count")):
                with patch("agent_router.send_response") as mock_send:
                    # Mock the request post to LLM generator
                    with patch("agent_router.requests.post") as mock_post:
                        mock_resp = MagicMock()
                        mock_resp.json.return_value = {"choices": [{"message": {"content": mock_gen_response}}]}
                        mock_post.return_value = mock_resp
                        
                        # Mock generalizer to avoid actual execution in background task
                        with patch("utils.generalizer.generalize_tool") as mock_gen:
                            line = json.dumps({"requestId": "789", "query": "insufficient query"})
                            await agent_router.handle_request(line)
                            
                            mock_send.assert_any_call("789", "processing", data={
                                "message": "Tool execution insufficient or unmatched (Missing subscribers count). Generating custom script...",
                                "confidence": 90,
                                "reasoning": "one lookup request"
                            })

@pytest.mark.asyncio
async def test_wil_pipeline_insufficient_fallback():
    # Test that when web_search_enabled is True but WIL pipeline returns an insufficient response,
    # it falls back to the toolkits and queries/routes tools.
    agent_router.ROUTE_CACHE.clear()
    agent_router.ROUTE_CACHE["insufficient query"] = {
        "match": True,
        "tool_calls": [
            {"tool_name": "lookup_youtube_stats", "arguments": {"channel_name": "@MrBeast"}}
        ],
        "confidence": 90,
        "reasoning": "one lookup request"
    }

    mock_registry = {
        "lookup_youtube_stats": {
            "name": "lookup_youtube_stats",
            "description": "YouTube stats details",
            "arguments": ["channel_name"]
        }
    }

    mock_wil_result = {
        "synthesized_response": "I could not find any information about MrBeast.",
        "sources": []
    }

    with patch("wil.pipeline.WILPipeline.run", return_value=mock_wil_result) as mock_wil_run:
        with patch("agent_router.load_registry_async", return_value=mock_registry):
            with patch("agent_router.execute_script", return_value=(True, {"subscribers": "100M"}, "")) as mock_exec:
                # First check_sufficiency is for WIL pipeline synthesized_response (returns False)
                # Second check_sufficiency is for tool combined_result (returns True)
                with patch("utils.sufficiency_checker.check_sufficiency") as mock_check_suff:
                    mock_check_suff.side_effect = [
                        (False, "Response indicates search failure"),
                        (True, "sufficient")
                    ]
                    with patch("agent_router.send_response") as mock_send:
                        line = json.dumps({
                            "requestId": "999",
                            "query": "insufficient query",
                            "web_search_enabled": True
                        })
                        await agent_router.handle_request(line)
                        
                        mock_wil_run.assert_called_once()
                        mock_exec.assert_called_once()
                        # Verify the retrying status message was sent
                        mock_send.assert_any_call("999", "processing", data={
                            "status": "wil_retrying",
                            "message": "Web search results insufficient (Response indicates search failure). Retrying with toolkits..."
                        })
                        # Verify final response success from fallback tool
                        success_calls = [c for c in mock_send.call_args_list if c[0][0] == "999" and c[0][1] == "success"]
                        assert len(success_calls) > 0

