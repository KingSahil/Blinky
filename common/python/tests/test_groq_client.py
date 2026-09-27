import io
import json
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image

import pytest

from ai.groq_client import (
    ask_groq_text,
    ask_groq_vision,
    _image_to_data_url,
    _parse_retry_wait_seconds,
    _is_rate_limit_error,
)


def response(ok: bool, payload: dict, status_code: int = 200, headers: dict | None = None) -> Mock:
    mocked = Mock()
    mocked.ok = ok
    mocked.status_code = status_code
    mocked.headers = headers or {}
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


def rate_limit_error(wait_s: float = 1.0) -> Mock:
    return response(
        False,
        {
            "error": {
                "code": "rate_limit_exceeded",
                "message": f"Rate limit reached on tokens per minute (TPM): Limit 8000. Please try again in {wait_s}s.",
            }
        },
        status_code=429,
        headers={"retry-after": str(wait_s)},
    )


def test_groq_vision_retries_without_response_format_after_json_validate_failed(tmp_path: Path) -> None:
    screenshot = tmp_path / "screen.jpg"
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(screenshot)

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


def test_groq_vision_retries_on_rate_limit_and_succeeds(tmp_path: Path) -> None:
    screenshot = tmp_path / "screen.png"
    img = Image.new("RGBA", (1920, 1080), color=(255, 0, 0, 255))
    img.save(screenshot)

    rate_err = rate_limit_error(wait_s=0.1)
    ok_resp = response(True, groq_body('{"summary":"Recovered after 429","steps":[]}'))

    with (
        patch.dict("os.environ", {"GROQ_API_KEY": "test-key", "BLINKY_GROQ_MODEL": "test-model"}),
        patch("ai.groq_client.requests.post", side_effect=[rate_err, ok_resp]) as post,
        patch("ai.groq_client.time.sleep") as mock_sleep,
    ):
        result = ask_groq_vision("Look at this", screenshot)

    assert result["summary"] == "Recovered after 429"
    assert post.call_count == 2
    mock_sleep.assert_called_once()


def test_groq_vision_raises_helpful_error_when_rate_limit_exceeded(tmp_path: Path) -> None:
    screenshot = tmp_path / "screen.png"
    img = Image.new("RGB", (200, 200), color="green")
    img.save(screenshot)

    rate_err1 = rate_limit_error(wait_s=0.1)
    rate_err2 = rate_limit_error(wait_s=0.1)
    rate_err3 = rate_limit_error(wait_s=0.1)

    with (
        patch.dict("os.environ", {"GROQ_API_KEY": "test-key", "BLINKY_GROQ_MODEL": "test-model"}),
        patch("ai.groq_client.requests.post", side_effect=[rate_err1, rate_err2, rate_err3]),
        patch("ai.groq_client.time.sleep"),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            ask_groq_vision("Look at this", screenshot)

    err_msg = str(exc_info.value)
    assert "rate_limit_exceeded" in err_msg
    assert "8,000 TPM" in err_msg or "TPM" in err_msg


def test_image_to_data_url_downscales_and_converts(tmp_path: Path) -> None:
    screenshot = tmp_path / "large_screen.png"
    large_img = Image.new("RGBA", (2560, 1440), color=(100, 150, 200, 255))
    large_img.save(screenshot)

    data_url = _image_to_data_url(screenshot, max_dimension=800, quality=75)
    assert data_url.startswith("data:image/jpeg;base64,")

    # Verify the generated JPEG is <= 800px on max dimension
    raw_b64 = data_url.split("base64,", 1)[1]
    import base64
    img_bytes = base64.b64decode(raw_b64)
    decoded_img = Image.open(io.BytesIO(img_bytes))
    assert max(decoded_img.size) <= 800
    assert decoded_img.format == "JPEG"


def test_parse_retry_wait_seconds() -> None:
    # 1. From header
    resp1 = response(False, {}, status_code=429, headers={"retry-after": "12.5"})
    assert _parse_retry_wait_seconds(resp1) == 12.5

    # 2. From x-ratelimit-reset-tokens header
    resp2 = response(False, {}, status_code=429, headers={"x-ratelimit-reset-tokens": "24.2s"})
    assert _parse_retry_wait_seconds(resp2) == 24.2

    # 3. From error message
    resp3 = response(False, {"error": {"message": "Limit 8000. Please try again in 18.5s."}}, status_code=429)
    assert _parse_retry_wait_seconds(resp3) == 18.5


def test_groq_vision_retries_as_text_when_messages_content_must_be_string(tmp_path: Path) -> None:
    screenshot = tmp_path / "screen.jpg"
    img = Image.new("RGB", (100, 100), color="red")
    img.save(screenshot)

    first = response(
        False,
        {
            "error": {
                "code": "invalid_request_error",
                "message": "messages[0].content must be a string",
            }
        },
        status_code=400,
    )
    second = response(True, groq_body('{"summary":"Parsed successfully from text","steps":[]}'))

    with (
        patch.dict("os.environ", {"GROQ_API_KEY": "test-key", "BLINKY_GROQ_MODEL": "openai/gpt-oss-120b"}),
        patch("ai.groq_client.requests.post", side_effect=[first, second]) as post,
    ):
        result = ask_groq_vision("Look at this screen and guide", screenshot)

    assert result["summary"] == "Parsed successfully from text"
    assert post.call_count == 2
    # First call had list content (multimodal)
    assert isinstance(post.call_args_list[0].kwargs["json"]["messages"][0]["content"], list)
    # Second call fallback had string content
    assert isinstance(post.call_args_list[1].kwargs["json"]["messages"][0]["content"], str)


def test_groq_vision_retries_with_default_model_when_model_not_found(tmp_path: Path) -> None:
    screenshot = tmp_path / "screen.jpg"
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(screenshot)

    not_found_err = response(
        False,
        {
            "error": {
                "code": "model_not_found",
                "message": "The model non-existent-model does not exist or you do not have access to it.",
            }
        },
        status_code=404,
    )
    ok_resp = response(True, groq_body('{"summary":"Recovered with default model","steps":[]}'))

    with (
        patch.dict("os.environ", {"GROQ_API_KEY": "test-key", "BLINKY_GROQ_VISION_MODEL": "non-existent-model"}),
        patch("ai.groq_client.requests.post", side_effect=[not_found_err, ok_resp]) as post,
    ):
        result = ask_groq_vision("Look at this screen", screenshot)

    assert result["summary"] == "Recovered with default model"
    assert post.call_count == 2
    assert post.call_args_list[0].kwargs["json"]["model"] == "non-existent-model"
    assert post.call_args_list[1].kwargs["json"]["model"] == "qwen/qwen3.8-27b"


