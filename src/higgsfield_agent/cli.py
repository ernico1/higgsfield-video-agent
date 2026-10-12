"""Command-line entry point: `higgsfield-agent "a brief"`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import anthropic
import higgsfield_client

from . import higgsfield
from .agent import log, run_agent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="higgsfield-agent",
        description="Generate a video with Higgsfield from a creative brief.",
    )
    parser.add_argument("brief", help="what the video should show, in any language")
    parser.add_argument("--image", help="first frame: https URL or local file (image-to-video)")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"), help="where to save the MP4")
    parser.add_argument("--max-videos", type=int, default=2, help="cap on billable generations per run")
    direct = parser.add_argument_group("direct mode (no Claude: the brief is sent as the prompt)")
    direct.add_argument("--direct", action="store_true", help="skip the agent and call Higgsfield once")
    direct.add_argument("--duration", type=int, default=5)
    direct.add_argument("--resolution", choices=higgsfield.RESOLUTIONS, default="720p")
    direct.add_argument("--aspect-ratio", choices=higgsfield.ASPECT_RATIOS, default="16:9")
    args = parser.parse_args(argv)

    if not higgsfield.has_credentials():
        print("Missing Higgsfield credentials: set HF_KEY to 'key-id:key-secret'.", file=sys.stderr)
        return 2

    try:
        if args.direct:
            video = higgsfield.generate_video(
                args.brief,
                image=args.image,
                duration=args.duration,
                resolution=args.resolution,
                aspect_ratio=args.aspect_ratio,
                output_dir=args.output_dir,
                on_status=log,
            )
            print(video.video_url)
            if video.local_path:
                print(video.local_path)
            return 0

        run = run_agent(args.brief, image=args.image, output_dir=args.output_dir, max_videos=args.max_videos)
    except anthropic.AuthenticationError:
        print("Claude rejected the credentials: check ANTHROPIC_API_KEY.", file=sys.stderr)
        return 2
    except anthropic.APIError as exc:
        print(f"Claude API error: {exc}", file=sys.stderr)
        return 1
    except (higgsfield.GenerationError, higgsfield_client.HiggsfieldClientError) as exc:
        print(f"Higgsfield error: {exc}", file=sys.stderr)
        return 1

    print(run.text)
    return 0 if run.videos else 1


if __name__ == "__main__":
    sys.exit(main())
