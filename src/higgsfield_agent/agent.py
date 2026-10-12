"""Claude-driven agent that turns a creative brief into Higgsfield videos."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from anthropic import beta_tool

from . import higgsfield

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """\
You are a video director's assistant. The user gives you a brief, in any language, and you \
produce the video with the generate_video tool, which calls the Higgsfield API (Kling 3.0 Turbo).

Every generate_video call spends the user's Higgsfield credits, and the run has a hard cap on \
the number of calls, so make each one count: decide on the shot before you call the tool rather \
than generating variations to compare.

Write the tool's prompt in English as one concrete shot description: subject, action, setting, \
lighting, camera movement and visual style. The video model sees only that prompt, not the \
conversation, so it has to stand on its own. Keep it under 2,000 characters.

Choose duration, resolution and aspect ratio from the brief (for example 9:16 for a TikTok or \
Reels clip). When the brief does not say, use 5 seconds, 720p and 16:9, which are the cheapest \
sensible settings. If the user supplies an image, pass it as `image` so the video starts from it.

If a call fails with a moderation or validation error, you may fix the request and try again \
once. If it fails for credentials, credits or the generation cap, stop and tell the user what \
they need to do.

Finish by replying in the user's language with the video URL, the local file path if there is \
one, and the settings you used. Report only URLs the tool returned.
"""


@dataclass
class AgentRun:
    text: str
    videos: list[higgsfield.VideoResult] = field(default_factory=list)


def log(message: str) -> None:
    print(f"[higgsfield] {message}", file=sys.stderr, flush=True)


def run_agent(
    brief: str,
    image: str | None = None,
    output_dir: Path | None = Path("outputs"),
    max_videos: int = 2,
    client: anthropic.Anthropic | None = None,
) -> AgentRun:
    """Run the agent on a brief. `max_videos` caps billable generations for the whole run."""
    client = client or anthropic.Anthropic()
    videos: list[higgsfield.VideoResult] = []
    attempts = 0

    @beta_tool
    def generate_video(
        prompt: str,
        image: str = "",
        duration: int = 5,
        resolution: str = "720p",
        aspect_ratio: str = "16:9",
    ) -> str:
        """Generate one video with Higgsfield and wait for the result. Billable; takes a few minutes.

        Args:
            prompt: English description of the shot. This is all the video model sees.
            image: Optional first frame: an https URL or a local file path. Leave empty for text-to-video.
            duration: Length in seconds, from 3 to 15.
            resolution: "720p" or "1080p".
            aspect_ratio: "16:9", "9:16" or "1:1". Ignored when an image is given (the image sets the ratio).
        """
        nonlocal attempts
        if attempts >= max_videos:
            return json.dumps({"error": f"Generation cap reached ({max_videos} per run). Do not call again."})
        attempts += 1
        try:
            video = higgsfield.generate_video(
                prompt,
                image=image or None,
                duration=duration,
                resolution=resolution,
                aspect_ratio=aspect_ratio,
                output_dir=output_dir,
                on_status=log,
            )
        except Exception as exc:  # reported to the model so it can correct the request or stop
            log(f"error: {exc}")
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        videos.append(video)
        return json.dumps(
            {
                "request_id": video.request_id,
                "model": video.model,
                "video_url": video.video_url,
                "local_path": str(video.local_path) if video.local_path else None,
            }
        )

    user_message = brief if not image else f"{brief}\n\nStarting image: {image}"
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        # On a safety-classifier decline, the API re-runs the request on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        tools=[generate_video],
        max_iterations=max_videos + 3,
        messages=[{"role": "user", "content": user_message}],
    )

    final = None
    for message in runner:
        final = message

    if final is None:
        return AgentRun(text="", videos=videos)
    if final.stop_reason == "refusal":
        return AgentRun(text="Claude declined this request.", videos=videos)
    text = "\n".join(block.text for block in final.content if block.type == "text")
    return AgentRun(text=text, videos=videos)
