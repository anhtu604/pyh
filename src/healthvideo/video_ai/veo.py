"""Live Google Vertex Veo transport behind an injectable HTTP boundary."""

from __future__ import annotations

import base64
import binascii
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from healthvideo.video_ai.base import VeoRequest, VeoResult

HttpCallable = Callable[
    [str, str, dict[str, str], object | None], tuple[int, object]
]


def _stdlib_http(
    method: str, url: str, headers: dict[str, str], payload: object | None
) -> tuple[int, object]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read()
    try:
        decoded: object = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        decoded = None
    return status, decoded


class GoogleVeoTransport:
    """Submit and poll one Veo request without exposing provider internals."""

    def __init__(
        self,
        *,
        project_id: str,
        location: str,
        token_provider: Callable[[], str],
        http: HttpCallable = _stdlib_http,
        max_polls: int = 120,
        poll_interval_seconds: float = 5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not project_id.strip() or not location.strip() or max_polls < 1:
            raise ValueError("Veo runtime configuration is invalid")
        self._project_id = project_id
        self._location = location
        self._token_provider = token_provider
        self._http = http
        self._max_polls = max_polls
        self._poll_interval_seconds = poll_interval_seconds
        self._sleep = sleep

    def generate(self, request: VeoRequest) -> VeoResult:
        token = self._token_provider()
        if not token.strip():
            raise ValueError("Veo access token is unavailable")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        base_url = f"https://{self._location}-aiplatform.googleapis.com/v1"
        model_path = (
            f"projects/{self._project_id}/locations/{self._location}/"
            f"publishers/google/models/{request.model}"
        )
        parameters: dict[str, object] = {
            "aspectRatio": request.aspect_ratio,
            "resolution": request.resolution,
            "durationSeconds": request.duration_seconds,
            "sampleCount": request.sample_count,
        }
        if request.requested_seed is not None:
            parameters["seed"] = request.requested_seed
        status, response = self._http(
            "POST",
            f"{base_url}/{model_path}:predictLongRunning",
            headers,
            {"instances": [{"prompt": request.prompt}], "parameters": parameters},
        )
        if status < 200 or status >= 300:
            raise ValueError("Veo submit request failed")
        operation = self._mapping(response).get("name")
        if not isinstance(operation, str) or not operation:
            raise ValueError("Veo response is missing operation identity")

        for poll_index in range(self._max_polls):
            status, polled = self._http(
                "GET", f"{base_url}/{operation}", headers, None
            )
            if status < 200 or status >= 300:
                raise ValueError("Veo poll request failed")
            operation_data = self._mapping(polled)
            if not operation_data.get("done"):
                if poll_index + 1 < self._max_polls:
                    self._sleep(self._poll_interval_seconds)
                continue
            if "error" in operation_data:
                raise ValueError("Veo generation operation failed")
            return self._decode_result(operation_data)
        raise TimeoutError("Veo generation timed out")

    @staticmethod
    def _mapping(value: object) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise TypeError("Veo returned a malformed response")
        return value

    @classmethod
    def _decode_result(cls, operation: Mapping[str, Any]) -> VeoResult:
        response = cls._mapping(operation.get("response"))
        videos = response.get("generatedVideos")
        if not isinstance(videos, list):
            raise TypeError("Veo response has no generated videos")
        if len(videos) != 1:
            raise ValueError("Veo must return exactly one generated video")
        item = cls._mapping(videos[0])
        video = cls._mapping(item.get("video"))
        mime_type = video.get("mimeType")
        if mime_type != "video/mp4":
            raise ValueError("Veo output MIME must be video/mp4")
        encoded = video.get("bytesBase64Encoded")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("Veo returned empty video content")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Veo output base64 is invalid") from error
        return VeoResult(video_bytes=content, mime_type="video/mp4")
