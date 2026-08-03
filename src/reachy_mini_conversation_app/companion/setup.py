"""Provision and activate a user-owned background assistant."""

import os
import sys
import json
import asyncio
import logging
import secrets
from enum import Enum
from pathlib import Path
from urllib.parse import quote, urlsplit

from reachy_mini_conversation_app.companion.client import CompanionClient, CompanionClientError
from reachy_mini_conversation_app.companion.settings import (
    CompanionSettings,
    read_companion_settings,
    write_companion_settings,
    normalize_companion_api_url,
)
from reachy_mini_conversation_app.companion.provisioner import (
    ASSISTANT_SPACE_NAME,
    ASSISTANT_BUCKET_NAME,
    DEFAULT_PROVISIONING_TIMEOUT,
)


logger = logging.getLogger(__name__)
PROVISIONER_MODULE = "reachy_mini_conversation_app.companion.provisioner"
MANAGED_API_HOST_SUFFIX = f"-{ASSISTANT_SPACE_NAME}.hf.space"
PROVISIONING_TIMEOUT_SECONDS = DEFAULT_PROVISIONING_TIMEOUT + 120.0
MAX_PROVISIONING_OUTPUT_BYTES = 8_192
VERIFICATION_ATTEMPTS = 5
VERIFICATION_RETRY_SECONDS = 2.0
_CHILD_CREDENTIAL_ENVIRONMENT = {
    "HF_TOKEN",
    "HF_ENDPOINT",
    "SMOL_ASSISTANT_API_TOKEN",
}


class CompanionSetupError(RuntimeError):
    """Report a safe background-assistant setup failure."""


class CompanionSetupState(str, Enum):
    """Describe the current setup phase without exposing credentials."""

    IDLE = "idle"
    PROVISIONING = "provisioning"
    VERIFYING = "verifying"
    RESTART_REQUIRED = "restart_required"
    FAILED = "failed"
    READY = "ready"


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    try:
        await process.communicate()
    except (BrokenPipeError, ConnectionResetError):
        await process.wait()


async def _run_provisioner(request: dict[str, object]) -> dict[str, object]:
    environment = os.environ.copy()
    for name in _CHILD_CREDENTIAL_ENVIRONMENT:
        environment.pop(name, None)

    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-m",
            PROVISIONER_MODULE,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
    except (OSError, NotImplementedError) as exc:
        raise CompanionSetupError("The bundled assistant setup could not start.") from exc

    encoded_request = json.dumps(request, separators=(",", ":")).encode()
    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(encoded_request),
            timeout=PROVISIONING_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        await _stop_process(process)
        raise CompanionSetupError("Hugging Face took too long to set up the assistant.") from exc
    except asyncio.CancelledError:
        await asyncio.shield(_stop_process(process))
        raise
    except OSError as exc:
        await _stop_process(process)
        raise CompanionSetupError("The bundled assistant setup stopped unexpectedly.") from exc

    if process.returncode != 0:
        raise CompanionSetupError("Hugging Face could not finish setting up the assistant.")
    if not stdout or len(stdout) > MAX_PROVISIONING_OUTPUT_BYTES:
        raise CompanionSetupError("The assistant setup returned an invalid response.")
    try:
        payload: object = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanionSetupError("The assistant setup returned an invalid response.") from exc
    if not isinstance(payload, dict):
        raise CompanionSetupError("The assistant setup returned an invalid response.")
    return payload


def _validate_resource_ids(space_id: str, bucket_id: str) -> str:
    space_owner, separator, space_name = space_id.partition("/")
    bucket_owner, bucket_separator, bucket_name = bucket_id.partition("/")
    if (
        not separator
        or not bucket_separator
        or not space_owner
        or space_owner != bucket_owner
        or space_name != ASSISTANT_SPACE_NAME
        or bucket_name != ASSISTANT_BUCKET_NAME
    ):
        raise CompanionSetupError("The assistant setup returned unexpected resources.")
    return space_owner


def _managed_resource_metadata(api_url: str) -> dict[str, str]:
    hostname = urlsplit(api_url).hostname or ""
    if not hostname.endswith(MANAGED_API_HOST_SUFFIX):
        return {}
    owner = hostname[: -len(MANAGED_API_HOST_SUFFIX)]
    if (
        not owner
        or not owner.isascii()
        or owner.startswith("-")
        or owner.endswith("-")
        or any(not (character.isalnum() or character == "-") for character in owner)
    ):
        return {}
    quoted_owner = quote(owner, safe="")
    return {
        "owner": owner,
        "space_url": f"https://huggingface.co/spaces/{quoted_owner}/{ASSISTANT_SPACE_NAME}",
        "bucket_url": f"https://huggingface.co/buckets/{quoted_owner}/{ASSISTANT_BUCKET_NAME}",
    }


async def provision_companion(
    hf_token: str,
    api_token: str,
) -> str:
    """Provision the signed-in user's canonical assistant."""
    payload = await _run_provisioner(
        {
            "hf_token": hf_token,
            "api_token": api_token,
        }
    )
    if set(payload) != {"space_id", "bucket_id", "api_url"}:
        raise CompanionSetupError("The assistant setup returned an invalid response.")
    space_id = payload["space_id"]
    bucket_id = payload["bucket_id"]
    api_url = payload["api_url"]
    if not isinstance(space_id, str) or not isinstance(bucket_id, str) or not isinstance(api_url, str):
        raise CompanionSetupError("The assistant setup returned an invalid response.")
    space_owner = _validate_resource_ids(space_id, bucket_id)
    try:
        normalized_api_url = normalize_companion_api_url(api_url, hosted_only=True)
    except ValueError as exc:
        raise CompanionSetupError("The assistant setup returned an invalid endpoint.") from exc
    expected_hostname = f"{space_owner}-{ASSISTANT_SPACE_NAME}.hf.space".lower()
    if urlsplit(normalized_api_url).hostname != expected_hostname:
        raise CompanionSetupError("The assistant setup returned an unexpected endpoint.")
    return normalized_api_url


class CompanionSetup:
    """Own one in-process setup job and its non-secret UI state."""

    def __init__(self, instance_path: str | Path | None) -> None:
        """Initialize setup state from the protected saved connection."""
        self._instance_path = instance_path
        settings = read_companion_settings(instance_path)
        self._resource_metadata = _managed_resource_metadata(settings.api_url) if settings.api_url else {}
        if settings.api_url is None:
            self._state = CompanionSetupState.IDLE
            self._message = "Create a private assistant and private storage in your Hugging Face account."
        else:
            self._state = CompanionSetupState.FAILED
            self._message = "The saved assistant is not active. Check your Hugging Face sign-in and try setup again."
        self._task: asyncio.Task[None] | None = None

    def status(self, *, configured: bool) -> dict[str, str]:
        """Return the current non-secret setup state for the UI."""
        if configured:
            status = {
                "state": CompanionSetupState.READY.value,
                "message": "Assistant ready for every personality.",
            }
        else:
            status = {"state": self._state.value, "message": self._message}
        status.update(self._resource_metadata)
        return status

    def set_connection_available(self, available: bool) -> None:
        """Update UI state after validating the saved assistant connection."""
        if available:
            settings = read_companion_settings(self._instance_path)
            self._resource_metadata = _managed_resource_metadata(settings.api_url) if settings.api_url else {}
            return
        self._state = CompanionSetupState.FAILED
        self._message = "The saved assistant is unavailable. Turn it on to reconnect or recreate it."
        self._resource_metadata = {}

    def start(self, hf_token: str) -> None:
        """Create or reconnect the signed-in user's assistant."""
        if self._task is not None and not self._task.done():
            return
        if self._state == CompanionSetupState.RESTART_REQUIRED:
            raise CompanionSetupError("Restart the Conversation App to finish setup.")
        self._state = CompanionSetupState.PROVISIONING
        self._message = "Preparing your private assistant and storage…"
        self._resource_metadata = {}
        self._task = asyncio.create_task(self._run(hf_token))

    async def _run(self, hf_token: str) -> None:
        try:
            api_token = secrets.token_urlsafe(32)
            api_url = await provision_companion(hf_token, api_token)
            self._resource_metadata = _managed_resource_metadata(api_url)
            self._state = CompanionSetupState.VERIFYING
            self._message = "Checking the private assistant connection…"
            client = CompanionClient(api_url, api_token, hf_token)
            try:
                for attempt in range(VERIFICATION_ATTEMPTS):
                    try:
                        await client.list_tasks()
                        break
                    except CompanionClientError:
                        if attempt == VERIFICATION_ATTEMPTS - 1:
                            raise
                        await asyncio.sleep(VERIFICATION_RETRY_SECONDS)
            finally:
                await client.close()
            write_companion_settings(
                self._instance_path,
                CompanionSettings(enabled=True, api_url=api_url, api_token=api_token),
            )
        except asyncio.CancelledError:
            raise
        except (CompanionSetupError, CompanionClientError, OSError, ValueError) as exc:
            logger.warning("Background assistant setup failed: %s", exc)
            self._state = CompanionSetupState.FAILED
            self._message = "Setup could not finish safely. Check your Hugging Face account and try again."
        except Exception:
            logger.exception("Background assistant setup failed unexpectedly")
            self._state = CompanionSetupState.FAILED
            self._message = "Setup could not finish safely. Check your Hugging Face account and try again."
        else:
            self._state = CompanionSetupState.RESTART_REQUIRED
            self._message = "Assistant set up. Restart the Conversation App to activate it."
        finally:
            self._task = None
