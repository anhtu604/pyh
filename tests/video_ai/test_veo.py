import base64

import pytest
from pydantic import ValidationError

from healthvideo.video_ai.base import VeoRequest, veo_request_sha256
from healthvideo.video_ai.veo import GoogleVeoTransport


def request(**changes: object) -> VeoRequest:
    return VeoRequest.model_validate(
        {"prompt": "Minh họa ít muối", "duration_seconds": 4} | changes
    )


def test_request_contract_and_hash_are_stable() -> None:
    first = request()
    assert first.model_dump(mode="json", exclude_none=True) == {
        "prompt": "Minh họa ít muối",
        "model": "veo-3.1-fast-generate-001",
        "aspect_ratio": "9:16",
        "resolution": "1080p",
        "duration_seconds": 4,
        "sample_count": 1,
    }
    assert veo_request_sha256(first) == veo_request_sha256(request())
    assert veo_request_sha256(first) != veo_request_sha256(request(requested_seed=7))
    with pytest.raises(ValidationError):
        request(duration_seconds=5)


def transport(
    replies: list[tuple[int, object]], *, token: str = "secret-token", polls: int = 3
) -> tuple[GoogleVeoTransport, list[tuple[str, str, dict[str, str], object]], list[int]]:
    calls: list[tuple[str, str, dict[str, str], object]] = []
    token_calls: list[int] = []

    def http(
        method: str, url: str, headers: dict[str, str], payload: object
    ) -> tuple[int, object]:
        calls.append((method, url, headers, payload))
        return replies.pop(0)

    def get_token() -> str:
        token_calls.append(1)
        return token

    return (
        GoogleVeoTransport(
            project_id="cloud-project",
            location="us-central1",
            token_provider=get_token,
            http=http,
            max_polls=polls,
            sleep=lambda _: None,
        ),
        calls,
        token_calls,
    )


def completed(content: bytes = b"mp4") -> dict[str, object]:
    return {
        "done": True,
        "response": {
            "generatedVideos": [
                {
                    "video": {
                        "bytesBase64Encoded": base64.b64encode(content).decode(),
                        "mimeType": "video/mp4",
                    }
                }
            ]
        },
    }


@pytest.mark.parametrize("duration", [4, 6, 8])
def test_submit_and_poll_exact_request(duration: int) -> None:
    live, calls, token_calls = transport(
        [(200, {"name": "operations/abc"}), (200, completed(b"video"))]
    )
    result = live.generate(request(duration_seconds=duration, requested_seed=11))

    assert result.video_bytes == b"video"
    assert token_calls == [1]
    assert calls[0][0] == "POST" and calls[1][0] == "GET"
    assert calls[0][2]["Authorization"] == "Bearer secret-token"
    assert calls[0][3] == {
        "instances": [{"prompt": "Minh họa ít muối"}],
        "parameters": {
            "aspectRatio": "9:16",
            "resolution": "1080p",
            "durationSeconds": duration,
            "sampleCount": 1,
            "seed": 11,
        },
    }


@pytest.mark.parametrize(
    "replies,match",
    [
        ([(500, {"error": "secret-token"})], "submit"),
        ([(200, {})], "operation"),
        ([(200, {"name": "op"}), (500, {})], "poll"),
        ([(200, {"name": "op"}), (200, {"done": True, "error": {}})], "failed"),
        ([(200, {"name": "op"}), (200, {"done": True, "response": {}})], "videos"),
        (
            [
                (200, {"name": "op"}),
                (200, {"done": True, "response": {"generatedVideos": [{}, {}]}}),
            ],
            "exactly one",
        ),
        (
            [
                (200, {"name": "op"}),
                (
                    200,
                    {
                        "done": True,
                        "response": {
                            "generatedVideos": [
                                {"video": {"bytesBase64Encoded": "!", "mimeType": "video/mp4"}}
                            ]
                        },
                    },
                ),
            ],
            "base64",
        ),
        (
            [
                (200, {"name": "op"}),
                (
                    200,
                    {
                        "done": True,
                        "response": {
                            "generatedVideos": [
                                {"video": {"bytesBase64Encoded": "eA==", "mimeType": "video/webm"}}
                            ]
                        },
                    },
                ),
            ],
            "MIME",
        ),
    ],
)
def test_provider_failures_are_sanitized(
    replies: list[tuple[int, object]], match: str
) -> None:
    live, _, _ = transport(replies)
    with pytest.raises((TypeError, ValueError), match=match) as raised:
        live.generate(request())
    assert "secret-token" not in str(raised.value)


def test_polling_is_bounded_and_empty_content_is_rejected() -> None:
    live, _, _ = transport(
        [(200, {"name": "op"}), (200, {"done": False}), (200, {"done": False})],
        polls=2,
    )
    with pytest.raises(TimeoutError):
        live.generate(request())

    live, _, _ = transport([(200, {"name": "op"}), (200, completed(b""))])
    with pytest.raises(ValueError, match="empty"):
        live.generate(request())
