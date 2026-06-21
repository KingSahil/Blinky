import json
from pathlib import Path
from unittest.mock import Mock, patch

from ai.groq_client import ask_groq_text, ask_groq_vision


def response(ok: bool, payload: dict, status_code: int = 200) -> Mock:
    mocked = Mock()
    mocked.ok = ok
    mocked.status_code = status_code
    mocked.text = json.dumps(payload)
    mocked.json.return_value = payload
    return mocked


def groq_body(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def json_validate_error() -> Mock:
    return response(
        False,
        {
            "error": {
                "code": "json_validate_failed",
                "message": "Failed to generate JSON. Please adjust your prompt.",
            }
        },
        status_code=400,
    )


def test_groq_vision_retries_without_response_format_after_json_validate_failed(tmp_path: Path) -> None:
    screenshot = tmp_path / "screen.jpg"
    screenshot.write_bytes(b"fake jpg")

    first = json_validate_error()
    second = response(True, groq_body('{"summary":"Done","steps":[]}'))

    with (
        patch.dict("os.environ", {"GROQ_API_KEY": "test-key", "BLINKY_GROQ_MODEL": "test-model"}),
        patch("ai.groq_client.requests.post", side_effect=[first, second]) as post,
    ):
        result = ask_groq_vision("Return JSON", screenshot)

    assert result == {"summary": "Done", "steps": [], "warnings": []}
    assert post.call_count == 2
    assert post.call_args_list[0].kwargs["json"]["response_format"] == {"type": "json_object"}
    assert "response_format" not in post.call_args_list[1].kwargs["json"]


def test_groq_text_retries_without_response_format_after_json_validate_failed() -> None:
    first = json_validate_error()
    second = response(True, groq_body('{"needs_screen":false,"is_continuation":false}'))

    with (
        patch.dict("os.environ", {"GROQ_API_KEY": "test-key", "BLINKY_GROQ_MODEL": "test-model"}),
        patch("ai.groq_client.requests.post", side_effect=[first, second]) as post,
    ):
        result = ask_groq_text("Return JSON")

    assert result == {"needs_screen": False, "is_continuation": False}
    assert post.call_count == 2
    assert post.call_args_list[0].kwargs["json"]["response_format"] == {"type": "json_object"}
    assert "response_format" not in post.call_args_list[1].kwargs["json"]
