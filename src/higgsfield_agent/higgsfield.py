"""Thin wrapper around the official Higgsfield SDK for video generation.

Docs: https://docs.higgsfield.ai/docs/models/video-generation
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import higgsfield_client
import httpx

# Endpoint IDs from the Higgsfield catalogue. Both share the same parameters,
# except `aspect_ratio` (text-to-video only) and `image_url` (image-to-video only).
TEXT_TO_VIDEO_MODEL = os.environ.get("HIGGSFIELD_T2V_MODEL", "kling-video/v3.0-turbo/text-to-video")
IMAGE_TO_VIDEO_MODEL = os.environ.get("HIGGSFIELD_I2V_MODEL", "kling-video/v3.0-turbo/image-to-video")

MIN_DURATION, MAX_DURATION = 3, 15
RESOLUTIONS = ("720p", "1080p")
ASPECT_RATIOS = ("16:9", "9:16", "1:1")

POLL_DELAY_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 15 * 60


class GenerationError(RuntimeError):
    """A generation request was rejected, failed, or timed out."""


@dataclass
class VideoResult:
    request_id: str
    model: str
    video_url: str
    local_path: Path | None = None


def has_credentials() -> bool:
    return bool(os.environ.get("HF_KEY") or (os.environ.get("HF_API_KEY") and os.environ.get("HF_API_SECRET")))


def resolve_image(image: str) -> str:
    """Return a public URL for `image`, uploading it first if it is a local file."""
    if urlparse(image).scheme in ("http", "https"):
        return image
    path = Path(image).expanduser()
    if not path.is_file():
        raise GenerationError(f"Image not found: {image} (expected an https URL or an existing local file)")
    return higgsfield_client.upload_file(path)


def build_request(
    prompt: str,
    image: str | None = None,
    duration: int = 5,
    resolution: str = "720p",
    aspect_ratio: str = "16:9",
) -> tuple[str, dict]:
    """Validate the parameters and return (endpoint id, arguments)."""
    if not prompt.strip():
        raise GenerationError("prompt must not be empty")
    if not MIN_DURATION <= duration <= MAX_DURATION:
        raise GenerationError(f"duration must be between {MIN_DURATION} and {MAX_DURATION} seconds")
    if resolution not in RESOLUTIONS:
        raise GenerationError(f"resolution must be one of {RESOLUTIONS}")

    arguments: dict = {"prompt": prompt, "duration": duration, "resolution": resolution}
    if image:
        arguments["image_url"] = resolve_image(image)
        return IMAGE_TO_VIDEO_MODEL, arguments
    if aspect_ratio not in ASPECT_RATIOS:
        raise GenerationError(f"aspect_ratio must be one of {ASPECT_RATIOS}")
    arguments["aspect_ratio"] = aspect_ratio
    return TEXT_TO_VIDEO_MODEL, arguments


def generate_video(
    prompt: str,
    image: str | None = None,
    duration: int = 5,
    resolution: str = "720p",
    aspect_ratio: str = "16:9",
    output_dir: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    on_status=None,
) -> VideoResult:
    """Submit a generation, wait for it, and optionally download the MP4."""
    model, arguments = build_request(prompt, image, duration, resolution, aspect_ratio)
    controller = higgsfield_client.submit(model, arguments=arguments)
    request_id = controller.request_id
    if on_status:
        on_status(f"submitted {request_id} to {model}")

    deadline = time.monotonic() + timeout
    last = None
    for status in controller.poll_request_status(delay=POLL_DELAY_SECONDS):
        name = type(status).__name__
        if name != last and on_status:
            on_status(name)
        last = name
        if isinstance(status, higgsfield_client.Completed):
            break
        if isinstance(status, higgsfield_client.NSFW):
            raise GenerationError(f"Request {request_id} was rejected by content moderation (not charged)")
        if isinstance(status, (higgsfield_client.Failed, higgsfield_client.Cancelled)):
            raise GenerationError(f"Request {request_id} ended as {name} (not charged)")
        if time.monotonic() > deadline:
            # The generation keeps running server-side; the request id lets the user recover it.
            raise GenerationError(f"Timed out after {timeout:.0f}s waiting for request {request_id}")

    result = controller.get()
    video_url = (result.get("video") or {}).get("url")
    if not video_url:
        raise GenerationError(f"Request {request_id} completed without a video URL: {result}")

    video = VideoResult(request_id=request_id, model=model, video_url=video_url)
    if output_dir is not None:
        video.local_path = download(video_url, output_dir / f"{request_id}.mp4")
    return video


def download(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
        response.raise_for_status()
        with destination.open("wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)
    return destination
