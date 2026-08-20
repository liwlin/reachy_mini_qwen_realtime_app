"""DashScope/Qwen Realtime API handler for low-latency audio conversation."""

import json
import uuid
import base64
import asyncio
import logging
from typing import Any, Final

import numpy as np
import websockets
from numpy.typing import NDArray
from scipy.signal import resample
from websockets.exceptions import ConnectionClosedError

from reachy_mini_conversation_app.config import (
    QWEN_AVAILABLE_VOICES,
    config,
    set_custom_profile,
    get_qwen_realtime_url,
    is_qwen_realtime_url_allowed,
)
from reachy_mini_conversation_app.prompts import get_session_voice, get_session_instructions
from reachy_mini_conversation_app.streaming import AdditionalOutputs, audio_to_int16
from reachy_mini_conversation_app.tools.core_tools import ToolSpec, ToolDependencies, get_tool_specs
from reachy_mini_conversation_app.conversation_handler import ConversationHandler
from reachy_mini_conversation_app.tools.background_tool_manager import (
    ToolCallRoutine,
    ToolNotification,
    BackgroundToolManager,
)


logger = logging.getLogger(__name__)

QWEN_INPUT_SAMPLE_RATE: Final[int] = 16000
QWEN_OUTPUT_SAMPLE_RATE: Final[int] = 24000
QWEN_MAX_BASE64_IMAGE_BYTES: Final[int] = 256 * 1024
QWEN_CAMERA_SILENCE_SAMPLES: Final[int] = QWEN_INPUT_SAMPLE_RATE // 10


def _openai_tool_specs_to_qwen(specs: list[ToolSpec]) -> list[dict[str, Any]]:
    """Convert this app's OpenAI-style tool specs to Qwen Realtime tool specs."""
    converted: list[dict[str, Any]] = []
    for spec in specs:
        function_spec: dict[str, Any] = {"name": spec["name"]}
        if "description" in spec:
            function_spec["description"] = spec["description"]
        if "parameters" in spec and spec["parameters"]:
            function_spec["parameters"] = spec["parameters"]
        converted.append({"type": "function", "function": function_spec})
    return converted


def _resolve_qwen_voice(profile_voice: str) -> str:
    """Map a profile voice name to a supported Qwen voice."""
    voice_map = {voice.lower(): voice for voice in QWEN_AVAILABLE_VOICES}
    return voice_map.get(profile_voice.lower(), "Tina")


def _json_get(obj: Any, *keys: str) -> Any:
    """Read nested dict attributes safely."""
    current = obj
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


class QwenRealtimeHandler(ConversationHandler):
    """DashScope/Qwen implementation of the shared realtime handler contract."""

    SAMPLE_RATE = QWEN_OUTPUT_SAMPLE_RATE

    def __init__(
        self,
        deps: ToolDependencies,
        instance_path: str | None = None,
        startup_voice: str | None = None,
    ) -> None:
        """Initialize the handler."""
        super().__init__()

        self.deps = deps
        self.instance_path = instance_path
        self._voice_override = _resolve_qwen_voice(startup_voice) if startup_voice else None

        self.websocket: Any = None
        self.output_queue: asyncio.Queue[tuple[int, NDArray[np.int16]] | AdditionalOutputs] = asyncio.Queue()
        self._input_buffer_lock = asyncio.Lock()

        self.tool_manager = BackgroundToolManager()

    def get_current_voice(self) -> str:
        """Return the resolved Qwen voice currently selected for this handler."""
        return _resolve_qwen_voice(self._voice_override or get_session_voice(self.instance_path))

    async def get_available_voices(self) -> list[str]:
        """Return the curated Qwen Realtime voices."""
        return list(QWEN_AVAILABLE_VOICES)

    async def apply_personality(self, profile: str | None) -> str:
        """Apply a new personality by updating the active session if connected."""
        try:
            set_custom_profile(profile)
            self._voice_override = None
            if self.websocket is not None:
                await self._send_session_update()
                return "Applied personality to Qwen realtime session."
            return "Applied personality. Will take effect on next connection."
        except Exception as e:
            logger.error("Error applying personality '%s': %s", profile, e)
            return f"Failed to apply personality: {e}"

    async def change_voice(self, voice: str) -> str:
        """Change only the voice and update the active session if connected."""
        self._voice_override = voice
        if self.websocket is not None:
            try:
                await self._send_session_update()
                return f"Voice changed to {voice}."
            except Exception as e:
                logger.warning("Failed to update Qwen voice: %s", e)
                return "Voice change failed. Will take effect on next connection."
        return "Voice changed. Will take effect on next connection."

    async def start_up(self) -> None:
        """Start the handler with minimal retries on unexpected websocket closure."""
        qwen_api_key = config.QWEN_API_KEY
        if not qwen_api_key or not qwen_api_key.strip():
            raise ValueError("DASHSCOPE_API_KEY (or QWEN_API_KEY) is required for Qwen Realtime")

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                await self._run_realtime_session(qwen_api_key)
                return
            except ConnectionClosedError as e:
                logger.warning("Qwen websocket closed unexpectedly (attempt %d/%d): %s", attempt, max_attempts, e)
                if attempt < max_attempts:
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                raise
            finally:
                self.websocket = None

    def _is_connected(self) -> bool:
        """Return whether the Qwen WebSocket is open."""
        return self.websocket is not None

    def _connect(self, url: str, headers: dict[str, str]) -> Any:
        """Return a Qwen WebSocket connection context."""
        return websockets.connect(
            url,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=20,
            proxy=None,
        )

    async def _send_event(self, event: dict[str, Any]) -> None:
        """Send a JSON event to Qwen Realtime."""
        if self.websocket is None:
            raise ConnectionError("Qwen websocket is not connected")
        await self.websocket.send(json.dumps(event, ensure_ascii=False))

    async def _send_session_update(self) -> None:
        """Send the current session configuration to Qwen Realtime."""
        session_config: dict[str, Any] = {
            "modalities": ["text", "audio"],
            "instructions": get_session_instructions(self.instance_path),
            "voice": self.get_current_voice(),
            "input_audio_format": "pcm",
            "output_audio_format": "pcm",
            "input_audio_transcription": {"model": "qwen3-asr-flash-realtime"},
            "turn_detection": {"type": "server_vad"},
            "tools": _openai_tool_specs_to_qwen(get_tool_specs()),
        }
        await self._send_event(
            {
                "event_id": f"event_{uuid.uuid4().hex}",
                "type": "session.update",
                "session": session_config,
            }
        )

    async def _run_realtime_session(self, qwen_api_key: str) -> None:
        """Establish and manage a single Qwen realtime session."""
        url = get_qwen_realtime_url()
        if not url:
            raise ValueError("Qwen realtime URL missing. Set QWEN_REALTIME_URL or QWEN_WORKSPACE_ID")
        if not is_qwen_realtime_url_allowed(url):
            raise ValueError("QWEN_REALTIME_URL must be an official Alibaba Cloud Qwen Realtime wss:// endpoint")

        headers = {"Authorization": f"Bearer {qwen_api_key}"}
        async with self._connect(url, headers) as websocket:
            self.websocket = websocket
            await self._send_session_update()
            logger.info(
                "Qwen realtime session initialized with model=%s voice=%s",
                config.QWEN_MODEL_NAME,
                self.get_current_voice(),
            )

            self.tool_manager.start_up(tool_callbacks=[self._handle_tool_result])
            try:
                async for raw_event in websocket:
                    try:
                        event = json.loads(raw_event)
                    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
                        logger.debug("Ignoring non-JSON Qwen event: %r", raw_event)
                        continue
                    if not isinstance(event, dict):
                        logger.debug("Ignoring non-object Qwen event: %r", event)
                        continue
                    await self._handle_server_event(event)
            finally:
                await self.tool_manager.shutdown()

    async def _handle_server_event(self, event: dict[str, Any]) -> None:
        """Handle one Qwen Realtime server event."""
        event_type = str(event.get("type", ""))
        logger.debug("Qwen event: %s", event_type)

        if event_type == "input_audio_buffer.speech_started":
            self._mark_activity("user_speech_started")
            if self._clear_queue is not None:
                self._clear_queue()
            self.deps.movement_manager.set_listening(True)
            return

        if event_type == "input_audio_buffer.speech_stopped":
            self._mark_activity("user_speech_stopped")
            self.deps.movement_manager.set_listening(False)
            return

        if event_type == "response.audio.done":
            self.deps.movement_manager.set_speaking(False)
            return

        if event_type == "conversation.item.input_audio_transcription.completed":
            transcript = str(event.get("transcript") or event.get("text") or "")
            if transcript:
                self._mark_activity("user_transcription_completed")
                await self.output_queue.put(AdditionalOutputs({"role": "user", "content": transcript}))
                self._emit_transcript("user", transcript, True)
            return

        if event_type == "response.audio_transcript.done":
            transcript = str(event.get("transcript") or event.get("text") or "")
            if transcript:
                self._mark_activity("assistant_transcript_done")
                await self.output_queue.put(AdditionalOutputs({"role": "assistant", "content": transcript}))
                self._emit_transcript("assistant", transcript, True)
            return

        if event_type == "response.audio.delta":
            audio_delta = event.get("delta")
            if isinstance(audio_delta, str) and audio_delta:
                self._mark_activity("assistant_audio_delta")
                self.deps.movement_manager.set_speaking(True)
                await self.output_queue.put(
                    (
                        QWEN_OUTPUT_SAMPLE_RATE,
                        np.frombuffer(base64.b64decode(audio_delta), dtype=np.int16).reshape(1, -1),
                    )
                )
            return

        if event_type == "response.function_call_arguments.done":
            self._mark_activity("tool_call_received")
            await self._start_tool_from_event(event)
            return

        if event_type == "error":
            error_payload = event.get("error")
            error_message = error_payload.get("message") if isinstance(error_payload, dict) else None
            msg = str(error_message or event.get("message") or "unknown error")
            logger.error("Qwen realtime error: %s", msg)
            await self.output_queue.put(AdditionalOutputs({"role": "assistant", "content": f"[error] {msg}"}))

    async def _start_tool_from_event(self, event: dict[str, Any]) -> None:
        """Start a background tool from a Qwen function-call event."""
        tool_name = event.get("name") or _json_get(event, "function", "name")
        args_json_str = event.get("arguments") or _json_get(event, "function", "arguments") or "{}"
        call_id = str(event.get("call_id") or event.get("id") or uuid.uuid4())

        if not isinstance(tool_name, str) or not isinstance(args_json_str, str):
            logger.error("Invalid Qwen tool call: name=%r args=%r call_id=%s", tool_name, args_json_str, call_id)
            return

        bg_tool = await self.tool_manager.start_tool(
            call_id=call_id,
            tool_call_routine=ToolCallRoutine(
                tool_name=tool_name,
                args_json_str=args_json_str,
                deps=self.deps,
            ),
            is_idle_tool_call=False,
        )
        await self.output_queue.put(
            AdditionalOutputs(
                {
                    "role": "assistant",
                    "content": f"🛠️ Used tool {tool_name} with args {args_json_str}. The tool is now running. Tool ID: {bg_tool.tool_id}",
                }
            )
        )

    async def _handle_tool_result(self, bg_tool: ToolNotification) -> None:
        """Send a completed background tool result back to Qwen."""
        if bg_tool.error is not None:
            tool_result: dict[str, Any] = {"error": bg_tool.error}
        elif bg_tool.result is not None:
            tool_result = dict(bg_tool.result)
        else:
            tool_result = {"error": "No result returned from tool execution"}

        if self.websocket is None:
            logger.warning("Qwen websocket closed during tool '%s' result; cannot send result back", bg_tool.tool_name)
            return

        image_b64 = tool_result.pop("b64_im", None)
        if bg_tool.tool_name == "camera" and isinstance(image_b64, str):
            if len(image_b64.encode("ascii", errors="ignore")) <= QWEN_MAX_BASE64_IMAGE_BYTES:
                async with self._input_buffer_lock:
                    await self._send_event(
                        {
                            "event_id": f"event_{uuid.uuid4().hex}",
                            "type": "session.update",
                            "session": {"turn_detection": None},
                        }
                    )
                    try:
                        silence = np.zeros(QWEN_CAMERA_SILENCE_SAMPLES, dtype=np.int16)
                        await self._send_event(
                            {
                                "event_id": f"event_{uuid.uuid4().hex}",
                                "type": "input_audio_buffer.append",
                                "audio": base64.b64encode(silence.tobytes()).decode("ascii"),
                            }
                        )
                        await self._send_event(
                            {
                                "event_id": f"event_{uuid.uuid4().hex}",
                                "type": "input_image_buffer.append",
                                "image": image_b64,
                            }
                        )
                        await self._send_event(
                            {
                                "event_id": f"event_{uuid.uuid4().hex}",
                                "type": "input_audio_buffer.commit",
                            }
                        )
                    finally:
                        await self._send_event(
                            {
                                "event_id": f"event_{uuid.uuid4().hex}",
                                "type": "session.update",
                                "session": {"turn_detection": {"type": "server_vad"}},
                            }
                        )
                tool_result["image"] = "Camera frame submitted to Qwen."
            else:
                tool_result["error"] = "Camera frame exceeds Qwen's 256 KB Base64 image limit."

        await self._send_event(
            {
                "event_id": f"event_{uuid.uuid4().hex}",
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": bg_tool.id,
                    "output": json.dumps(tool_result, ensure_ascii=False),
                },
            }
        )

        await self.output_queue.put(
            AdditionalOutputs(
                {
                    "role": "assistant",
                    "content": json.dumps(tool_result, ensure_ascii=False),
                    "metadata": {
                        "title": f"🛠️ Used tool {bg_tool.tool_name}",
                        "status": "done",
                    },
                }
            )
        )

        await self._send_event(
            {
                "event_id": f"event_{uuid.uuid4().hex}",
                "type": "response.create",
            }
        )

    async def receive(self, frame: tuple[int, NDArray[np.int16]]) -> None:
        """Receive audio frame from the microphone and send it to Qwen."""
        if self.websocket is None:
            return

        input_sample_rate, audio_frame = frame
        if audio_frame.ndim == 2:
            if audio_frame.shape[1] > audio_frame.shape[0]:
                audio_frame = audio_frame.T
            if audio_frame.shape[1] > 1:
                audio_frame = audio_frame[:, 0]

        if QWEN_INPUT_SAMPLE_RATE != input_sample_rate:
            audio_frame = resample(audio_frame, int(len(audio_frame) * QWEN_INPUT_SAMPLE_RATE / input_sample_rate))

        audio_frame = audio_to_int16(audio_frame)
        self._mark_activity("microphone_audio")
        audio_message = base64.b64encode(audio_frame.tobytes()).decode("utf-8")
        try:
            async with self._input_buffer_lock:
                await self._send_event(
                    {
                        "event_id": f"event_{uuid.uuid4().hex}",
                        "type": "input_audio_buffer.append",
                        "audio": audio_message,
                    }
                )
        except Exception as e:
            logger.debug("Dropping Qwen audio frame: connection not ready (%s)", e)

    async def say(self, text: str) -> None:
        """Reject injected text turns until Qwen exposes a safe message event."""
        raise NotImplementedError("Qwen Realtime text injection is not supported")

    async def shutdown(self) -> None:
        """Shutdown the handler."""
        await self.tool_manager.shutdown()
        if self.websocket is not None:
            try:
                await self.websocket.close()
            except ConnectionClosedError as e:
                logger.debug("Qwen websocket already closed during shutdown: %s", e)
            except Exception as e:
                logger.debug("Qwen websocket close ignored: %s", e)
            finally:
                self.websocket = None

        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
