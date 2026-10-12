import json
from types import SimpleNamespace

import higgsfield_client
import pytest

from higgsfield_agent import agent, higgsfield


class FakeController:
    request_id = "req-1"

    def __init__(self, statuses, result):
        self._statuses, self._result = statuses, result

    def poll_request_status(self, delay):
        yield from self._statuses

    def get(self):
        return self._result


def test_text_to_video_request():
    model, args = higgsfield.build_request("a cat", duration=8, resolution="1080p", aspect_ratio="9:16")
    assert model == higgsfield.TEXT_TO_VIDEO_MODEL
    assert args == {"prompt": "a cat", "duration": 8, "resolution": "1080p", "aspect_ratio": "9:16"}


def test_image_to_video_request_omits_aspect_ratio():
    model, args = higgsfield.build_request("a cat", image="https://example.com/cat.jpg")
    assert model == higgsfield.IMAGE_TO_VIDEO_MODEL
    assert args["image_url"] == "https://example.com/cat.jpg"
    assert "aspect_ratio" not in args


@pytest.mark.parametrize("kwargs", [{"duration": 2}, {"duration": 16}, {"resolution": "4k"}, {"aspect_ratio": "4:3"}])
def test_invalid_parameters_rejected_before_submitting(kwargs):
    with pytest.raises(higgsfield.GenerationError):
        higgsfield.build_request("a cat", **kwargs)


def test_generate_video_returns_url(monkeypatch):
    controller = FakeController(
        [higgsfield_client.Queued(), higgsfield_client.InProgress(), higgsfield_client.Completed()],
        {"video": {"url": "https://cdn.example.com/v.mp4"}},
    )
    monkeypatch.setattr(higgsfield_client, "submit", lambda model, arguments: controller)
    video = higgsfield.generate_video("a cat")
    assert (video.request_id, video.video_url) == ("req-1", "https://cdn.example.com/v.mp4")


def test_generate_video_raises_on_moderation(monkeypatch):
    controller = FakeController([higgsfield_client.NSFW()], {})
    monkeypatch.setattr(higgsfield_client, "submit", lambda model, arguments: controller)
    with pytest.raises(higgsfield.GenerationError, match="moderation"):
        higgsfield.generate_video("a cat")


def test_agent_enforces_generation_cap(monkeypatch):
    calls = []

    def fake_generate(prompt, **kwargs):
        calls.append(prompt)
        return higgsfield.VideoResult("req-1", "m", "https://cdn.example.com/v.mp4")

    monkeypatch.setattr(higgsfield, "generate_video", fake_generate)

    class FakeMessages:
        def tool_runner(self, tools, **kwargs):
            tool = tools[0]
            first = json.loads(tool.call({"prompt": "one"}))
            second = json.loads(tool.call({"prompt": "two"}))
            assert "video_url" in first and "cap reached" in second["error"]
            return iter([SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="done")])])

    client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))
    run = agent.run_agent("brief", max_videos=1, client=client)
    assert calls == ["one"] and run.text == "done" and len(run.videos) == 1
