import json
import base64
import asyncio
from unittest.mock import MagicMock

import numpy as np
import pytest

from reachy_mini_conversation_app import config as config_mod
from reachy_mini_conversation_app import qwen_realtime as qwen_realtime_mod
from reachy_mini_conversation_app.streaming import AdditionalOutputs
from reachy_mini_conversation_app.qwen_realtime import QwenRealtimeHandler
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.conversation_handler import ConversationHandler
from reachy_mini_conversation_app.tools.tool_constants import ToolState
from reachy_mini_conversation_app.tools.background_tool_manager import ToolNotification


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    async def close(self) -> None:
        return None


class _BlockingImageWebSocket(_FakeWebSocket):
    def __init__(self) -> None:
        super().__init__()
        self.image_started = asyncio.Event()
        self.release_image = asyncio.Event()

    async def send(self, payload: str) -> None:
        event = json.loads(payload)
        self.sent.append(event)
        if event["type"] == "input_image_buffer.append":
            self.image_started.set()
            await self.release_image.wait()


class _FailingImageWebSocket(_FakeWebSocket):
    async def send(self, payload: str) -> None:
        event = json.loads(payload)
        self.sent.append(event)
        if event["type"] == "input_image_buffer.append":
            raise ConnectionError("image send failed")


def _handler() -> QwenRealtimeHandler:
    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())
    deps.movement_manager.is_idle.return_value = False
    return QwenRealtimeHandler(deps)


def test_qwen_handler_implements_shared_conversation_contract() -> None:
    """The Qwen provider conforms to the shared handler boundary."""
    assert isinstance(_handler(), ConversationHandler)


def test_qwen_url_builds_from_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    """A workspace ID builds the official regional Qwen WebSocket URL."""
    monkeypatch.setattr(config_mod.config, "QWEN_REALTIME_URL", None)
    monkeypatch.setattr(config_mod.config, "QWEN_WORKSPACE_ID", "workspace-test")
    monkeypatch.setattr(config_mod.config, "QWEN_REGION", "cn-beijing")
    monkeypatch.setattr(config_mod.config, "QWEN_MODEL_NAME", "qwen3.5-omni-flash-realtime")

    assert config_mod.get_qwen_realtime_url() == (
        "wss://workspace-test.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime?model=qwen3.5-omni-flash-realtime"
    )


@pytest.mark.asyncio
async def test_qwen_session_update_uses_pcm_and_nested_tools() -> None:
    """Qwen receives PCM formats and its required nested function schema."""
    handler = _handler()
    websocket = _FakeWebSocket()
    handler.websocket = websocket

    await handler._send_session_update()

    event = websocket.sent[0]
    session = event["session"]
    assert isinstance(session, dict)
    assert session["input_audio_format"] == "pcm"
    assert session["output_audio_format"] == "pcm"
    assert session["turn_detection"] == {"type": "server_vad"}
    assert all("function" in tool for tool in session["tools"])


def test_qwen_connection_bypasses_system_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """The realtime socket avoids system proxies that break direct TLS."""
    connect = MagicMock(return_value=object())
    monkeypatch.setattr("reachy_mini_conversation_app.qwen_realtime.websockets.connect", connect)

    result = _handler()._connect("wss://workspace.example", {"Authorization": "Bearer test"})

    assert result is connect.return_value
    assert connect.call_args.kwargs["proxy"] is None


def test_qwen_connection_bounds_close_handshake(monkeypatch: pytest.MonkeyPatch) -> None:
    """A backend restart must not consume the personality RPC timeout while closing Qwen."""
    connect = MagicMock(return_value=object())
    monkeypatch.setattr("reachy_mini_conversation_app.qwen_realtime.websockets.connect", connect)

    result = _handler()._connect("wss://workspace.example", {"Authorization": "Bearer test"})

    assert result is connect.return_value
    assert connect.call_args.kwargs["close_timeout"] == 2.0


@pytest.mark.asyncio
async def test_qwen_idle_keepalive_requests_a_server_event_before_stream_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An idle session must elicit a server reply before the 300-second timeout."""
    handler = _handler()
    websocket = _FakeWebSocket()
    handler.websocket = websocket
    sleeps: list[float] = []

    async def no_wait(delay: float) -> None:
        sleeps.append(delay)

    original_send = websocket.send

    async def send_once(payload: str) -> None:
        await original_send(payload)
        handler.websocket = None

    monkeypatch.setattr("reachy_mini_conversation_app.qwen_realtime.asyncio.sleep", no_wait)
    websocket.send = send_once  # type: ignore[method-assign]

    await handler._keepalive_loop()

    assert len(sleeps) == 1
    assert 0 < sleeps[0] < 300
    assert websocket.sent == [
        {
            "event_id": websocket.sent[0]["event_id"],
            "type": "session.update",
            "session": {"turn_detection": {"type": "server_vad"}},
        }
    ]


@pytest.mark.asyncio
async def test_qwen_audio_and_transcripts_feed_shared_outputs() -> None:
    """Qwen audio and transcripts flow through the shared output contract."""
    handler = _handler()
    observed: list[tuple[str, str, bool]] = []
    handler.set_transcript_observer(lambda role, text, final: observed.append((role, text, final)))
    audio_bytes = np.array([1, 2, 3], dtype=np.int16).tobytes()

    await handler._handle_server_event(
        {"type": "response.audio.delta", "delta": base64.b64encode(audio_bytes).decode()}
    )
    await handler._handle_server_event({"type": "response.audio_transcript.done", "transcript": "hello"})

    audio_output = await handler.output_queue.get()
    transcript_output = await handler.output_queue.get()
    assert audio_output[0] == 24000
    assert np.array_equal(audio_output[1], np.array([1, 2, 3], dtype=np.int16).reshape(1, -1))
    assert isinstance(transcript_output, AdditionalOutputs)
    assert observed == [("assistant", "hello", True)]


@pytest.mark.asyncio
async def test_camera_result_commits_image_in_manual_mode_then_restores_vad() -> None:
    """Camera input uses manual commit before restoring server VAD."""
    handler = _handler()
    websocket = _FakeWebSocket()
    handler.websocket = websocket
    image_b64 = base64.b64encode(b"jpeg-data").decode()
    notification = ToolNotification(
        id="call_camera",
        tool_name="camera",
        is_idle_tool_call=False,
        status=ToolState.COMPLETED,
        result={"b64_im": image_b64},
    )

    await handler._handle_tool_result(notification)

    assert [event["type"] for event in websocket.sent] == [
        "session.update",
        "input_audio_buffer.append",
        "input_image_buffer.append",
        "input_audio_buffer.commit",
        "session.update",
        "conversation.item.create",
        "response.create",
    ]
    assert websocket.sent[0]["session"] == {"turn_detection": None}
    assert websocket.sent[4]["session"] == {"turn_detection": {"type": "server_vad"}}
    assert image_b64 not in json.dumps(websocket.sent[5])


def test_oversized_qwen_image_is_reencoded_below_the_api_limit() -> None:
    """An oversized SDK JPEG is recompressed instead of being rejected outright."""
    fit_image = getattr(qwen_realtime_mod, "_fit_qwen_image_base64", None)
    assert fit_image is not None
    raw_image = b"oversized-jpeg" * 20000
    original_b64 = base64.b64encode(raw_image).decode("ascii")
    encoded_inputs: list[bytes] = []

    def reencode(jpeg_bytes: bytes) -> bytes:
        encoded_inputs.append(jpeg_bytes)
        return b"small-jpeg"

    fitted_b64 = fit_image(original_b64, reencode=reencode)

    assert encoded_inputs == [raw_image]
    assert fitted_b64 == base64.b64encode(b"small-jpeg").decode("ascii")


@pytest.mark.asyncio
async def test_camera_result_reencodes_oversized_image_before_append(monkeypatch: pytest.MonkeyPatch) -> None:
    """The camera turn sends the fitted frame through the normal Qwen manual-VAD flow."""
    handler = _handler()
    websocket = _FakeWebSocket()
    handler.websocket = websocket
    oversized_b64 = base64.b64encode(b"x" * (256 * 1024)).decode("ascii")
    fitted_b64 = base64.b64encode(b"small-jpeg").decode("ascii")
    monkeypatch.setattr(qwen_realtime_mod, "_fit_qwen_image_base64", lambda _image: fitted_b64, raising=False)
    notification = ToolNotification(
        id="call_camera",
        tool_name="camera",
        is_idle_tool_call=False,
        status=ToolState.COMPLETED,
        result={"b64_im": oversized_b64},
    )

    await handler._handle_tool_result(notification)

    image_events = [event for event in websocket.sent if event["type"] == "input_image_buffer.append"]
    assert image_events == [
        {
            "event_id": image_events[0]["event_id"],
            "type": "input_image_buffer.append",
            "image": fitted_b64,
        }
    ]


@pytest.mark.asyncio
async def test_camera_turn_blocks_microphone_frames_until_vad_is_restored() -> None:
    """A live microphone frame cannot enter the manual camera commit."""
    handler = _handler()
    websocket = _BlockingImageWebSocket()
    handler.websocket = websocket
    notification = ToolNotification(
        id="call_camera",
        tool_name="camera",
        is_idle_tool_call=False,
        status=ToolState.COMPLETED,
        result={"b64_im": base64.b64encode(b"jpeg-data").decode()},
    )

    camera_task = asyncio.create_task(handler._handle_tool_result(notification))
    await websocket.image_started.wait()
    microphone_task = asyncio.create_task(handler.receive((16000, np.array([7, 8], dtype=np.int16))))
    await asyncio.sleep(0)

    assert [event["type"] for event in websocket.sent].count("input_audio_buffer.append") == 1

    websocket.release_image.set()
    await camera_task
    await microphone_task
    event_types = [event["type"] for event in websocket.sent]
    restore_index = event_types.index("session.update", 1)
    assert event_types.index("input_audio_buffer.append", 2) > restore_index


@pytest.mark.asyncio
async def test_camera_turn_restores_vad_when_image_send_fails() -> None:
    """A failed camera upload cannot leave the session in manual VAD mode."""
    handler = _handler()
    websocket = _FailingImageWebSocket()
    handler.websocket = websocket
    notification = ToolNotification(
        id="call_camera",
        tool_name="camera",
        is_idle_tool_call=False,
        status=ToolState.COMPLETED,
        result={"b64_im": base64.b64encode(b"jpeg-data").decode()},
    )

    with pytest.raises(ConnectionError, match="image send failed"):
        await handler._handle_tool_result(notification)

    assert websocket.sent[-1] == {
        "event_id": websocket.sent[-1]["event_id"],
        "type": "session.update",
        "session": {"turn_detection": {"type": "server_vad"}},
    }


@pytest.mark.asyncio
async def test_qwen_say_is_explicitly_unsupported() -> None:
    """RPC text injection fails clearly instead of mutating session instructions."""
    handler = _handler()
    websocket = _FakeWebSocket()
    handler.websocket = websocket

    with pytest.raises(NotImplementedError, match="text injection"):
        await handler.say("hello")

    assert websocket.sent == []


@pytest.mark.asyncio
async def test_qwen_startup_requires_dashscope_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Qwen startup fails clearly when the DashScope key is absent."""
    monkeypatch.setattr(config_mod.config, "QWEN_API_KEY", None)

    with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
        await _handler().start_up()
