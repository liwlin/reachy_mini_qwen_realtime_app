import json
import base64
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from fastrtc import AdditionalOutputs

import reachy_mini_conversation_app.qwen_realtime as qwen_mod
from reachy_mini_conversation_app.config import config, get_qwen_realtime_url
from reachy_mini_conversation_app.qwen_realtime import (
    QwenRealtimeHandler,
    _openai_tool_specs_to_qwen,
)
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.tools.tool_constants import ToolState
from reachy_mini_conversation_app.tools.background_tool_manager import ToolNotification


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed = False

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    async def close(self) -> None:
        self.closed = True


def _handler() -> QwenRealtimeHandler:
    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())
    deps.movement_manager.is_idle.return_value = False
    return QwenRealtimeHandler(deps)


def test_openai_tool_specs_convert_to_qwen_nested_function_schema() -> None:
    """Existing flat tool specs should convert to Qwen's nested schema."""
    specs = [
        {
            "type": "function",
            "name": "dance",
            "description": "Start a dance",
            "parameters": {"type": "object", "properties": {"name": {"type": "string"}}},
        }
    ]

    assert _openai_tool_specs_to_qwen(specs) == [
        {
            "type": "function",
            "function": {
                "name": "dance",
                "description": "Start a dance",
                "parameters": {"type": "object", "properties": {"name": {"type": "string"}}},
            },
        }
    ]


def test_qwen_realtime_url_builds_from_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Workspace and region settings should build an official endpoint."""
    monkeypatch.setattr(config, "QWEN_REALTIME_URL", None)
    monkeypatch.setattr(config, "QWEN_WORKSPACE_ID", "ws-test")
    monkeypatch.setattr(config, "QWEN_REGION", "ap-southeast-1")
    monkeypatch.setattr(config, "MODEL_NAME", "qwen3.5-omni-flash-realtime")

    assert (
        get_qwen_realtime_url()
        == "wss://ws-test.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/realtime?model=qwen3.5-omni-flash-realtime"
    )


@pytest.mark.asyncio
async def test_qwen_session_update_uses_realtime_audio_schema() -> None:
    """Session updates should use the current flat PCM field schema."""
    handler = _handler()
    websocket = _FakeWebSocket()
    handler.websocket = websocket

    await handler._send_session_update()

    assert websocket.sent
    event = websocket.sent[0]
    session = event["session"]
    assert event["type"] == "session.update"
    assert session["input_audio_format"] == "pcm"
    assert session["output_audio_format"] == "pcm"
    assert session["input_audio_transcription"] == {"model": "qwen3-asr-flash-realtime"}
    assert "audio" not in session
    assert "enable_input_audio_transcription" not in session


@pytest.mark.asyncio
async def test_qwen_send_event_fails_explicitly_without_connection() -> None:
    """Non-audio callers should see a closed connection instead of a silent drop."""
    handler = _handler()

    with pytest.raises(ConnectionError, match="not connected"):
        await handler._send_event({"type": "session.update"})


def test_qwen35_uses_tina_as_the_default_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsupported profile voices should fall back to Qwen 3.5's Tina voice."""
    monkeypatch.setattr(qwen_mod, "get_session_voice", lambda: "cedar")

    assert _handler().get_current_voice() == "Tina"


def test_qwen_connection_bypasses_system_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Qwen must connect directly when the robot's optional local proxy is offline."""
    connect = MagicMock(return_value=object())
    monkeypatch.setattr(qwen_mod.websockets, "connect", connect)

    result = _handler()._connect("wss://workspace.example", {"Authorization": "Bearer test"})

    assert result is connect.return_value
    connect.assert_called_once_with(
        "wss://workspace.example",
        additional_headers={"Authorization": "Bearer test"},
        ping_interval=20,
        ping_timeout=20,
        proxy=None,
    )


@pytest.mark.asyncio
async def test_qwen_receive_sends_pcm16_audio_event() -> None:
    """Microphone frames should be sent as Base64 PCM16 audio events."""
    handler = _handler()
    websocket = _FakeWebSocket()
    handler.websocket = websocket

    await handler.receive((16000, np.array([0, 1000, -1000], dtype=np.int16)))

    assert websocket.sent
    event = websocket.sent[0]
    assert event["type"] == "input_audio_buffer.append"
    assert base64.b64decode(event["audio"]) == np.array([0, 1000, -1000], dtype=np.int16).tobytes()


@pytest.mark.asyncio
async def test_qwen_audio_and_transcript_events_queue_outputs() -> None:
    """Native Qwen response events should feed audio and transcript outputs."""
    handler = _handler()
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
    assert transcript_output.args[0] == {"role": "assistant", "content": "hello"}


@pytest.mark.asyncio
async def test_qwen_tool_result_sends_function_output_and_response_create() -> None:
    """Tool results should be returned before requesting the follow-up response."""
    handler = _handler()
    websocket = _FakeWebSocket()
    handler.websocket = websocket

    notification = ToolNotification(
        id="call_1",
        tool_name="look_up",
        is_idle_tool_call=False,
        status=ToolState.COMPLETED,
        result={"answer": 42},
    )

    await handler._handle_tool_result(notification)

    assert [event["type"] for event in websocket.sent] == ["conversation.item.create", "response.create"]
    assert websocket.sent[0]["item"]["call_id"] == "call_1"
    assert json.loads(websocket.sent[0]["item"]["output"]) == {"answer": 42}
    assert set(websocket.sent[1]) == {"event_id", "type"}


@pytest.mark.asyncio
async def test_qwen_camera_result_uses_image_buffer_without_leaking_base64_in_tool_output() -> None:
    """Camera bytes should use the image buffer and stay out of tool output."""
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
    assert websocket.sent[0]["session"]["turn_detection"] is None
    assert websocket.sent[2]["image"] == image_b64
    assert websocket.sent[4]["session"]["turn_detection"] == {"type": "server_vad"}
    tool_output = json.loads(websocket.sent[5]["item"]["output"])
    assert tool_output == {"image": "Camera frame submitted to Qwen."}
    assert image_b64 not in websocket.sent[5]["item"]["output"]
    assert notification.result == {"b64_im": image_b64}


@pytest.mark.asyncio
async def test_qwen_startup_rejects_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Startup should fail clearly rather than use a placeholder credential."""
    monkeypatch.setattr(config, "QWEN_API_KEY", None)

    with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
        await _handler().start_up()


@pytest.mark.asyncio
async def test_qwen_tool_call_starts_background_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Completed Qwen arguments should dispatch exactly one background tool."""
    handler = _handler()
    start_tool = AsyncMock()
    bg_tool = MagicMock()
    bg_tool.tool_id = "tool-id"
    start_tool.return_value = bg_tool
    tool_manager = MagicMock()
    tool_manager.start_tool = start_tool
    monkeypatch.setattr(handler, "tool_manager", tool_manager)

    await handler._handle_server_event(
        {
            "type": "response.function_call_arguments.done",
            "name": "dance",
            "arguments": '{"name":"salsa"}',
            "call_id": "call_2",
        }
    )

    start_tool.assert_awaited_once()
    kwargs = start_tool.await_args.kwargs
    assert kwargs["call_id"] == "call_2"
    assert kwargs["tool_call_routine"].tool_name == "dance"
    assert kwargs["tool_call_routine"].args_json_str == '{"name":"salsa"}'
