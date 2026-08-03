import sys
import json
import logging
from enum import Enum
from math import isfinite
from typing import TextIO
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urlparse

from huggingface_hub import HfApi, Volume, SpaceStage
from huggingface_hub.errors import (
    HfHubHTTPError,
    BucketNotFoundError,
    RepositoryNotFoundError,
    RemoteEntryNotFoundError,
)


ASSISTANT_API_TOKEN_ENV = "SMOL_ASSISTANT_API_TOKEN"
ASSISTANT_SPACE_NAME = "smolagents-assistant-reachy-mini"
ASSISTANT_BUCKET_NAME = "smolagents-assistant-reachy-mini-data"
STATE_MOUNT_PATH = "/data"
DEFAULT_PROVISIONING_TIMEOUT = 900.0
MIN_API_TOKEN_CHARS = 32
MAX_TOKEN_CHARS = 4_096
MAX_PROVISIONING_REQUEST_CHARS = 32_768
ASSISTANT_DOCKERFILE = (
    b"FROM ghcr.io/alozowski/smolagents-assistant@"
    b"sha256:d04e612bc928398a320bc632de88c9927994cf24a508226e49a574ee216440bf\n\n"
    b'CMD ["smol-assistant", "--state-dir", "/data", "service", "--web"]\n'
)
logger = logging.getLogger(__name__)


class ProvisioningError(RuntimeError):
    """Report an assistant provisioning failure."""


class AssistantDiscoveryState(str, Enum):
    """Describe whether the canonical assistant resources exist."""

    ABSENT = "absent"
    BUCKET_ONLY = "bucket_only"
    MANAGED = "managed"


@dataclass(frozen=True, slots=True)
class AssistantDiscovery:
    """Describe canonical assistant resources without retaining credentials."""

    state: AssistantDiscoveryState
    space_id: str
    bucket_id: str
    dockerfile_missing: bool


@dataclass(frozen=True, slots=True)
class ProvisionedAssistant:
    """Describe a provisioned assistant without retaining credentials."""

    space_id: str
    bucket_id: str
    api_url: str


class ProvisioningRequestError(ValueError):
    """Report invalid trusted-client input."""


def _is_visible_ascii(value: str, min_chars: int) -> bool:
    return (
        min_chars <= len(value) <= MAX_TOKEN_CHARS
        and value.isascii()
        and all(0x21 <= ord(character) <= 0x7E for character in value)
    )


def _inspect_assistant(api: HfApi) -> tuple[AssistantDiscovery, str | None]:
    identity = api.whoami()
    username = identity.get("name")
    if not isinstance(username, str) or not username:
        raise ProvisioningError("Hugging Face did not return an account name.")

    bucket_id = f"{username}/{ASSISTANT_BUCKET_NAME}"
    space_id = f"{username}/{ASSISTANT_SPACE_NAME}"
    try:
        bucket = api.bucket_info(bucket_id)
    except BucketNotFoundError:
        bucket = None
    try:
        space = api.space_info(space_id)
    except RepositoryNotFoundError:
        space = None

    if bucket is not None and (bucket.id != bucket_id or not bucket.private):
        raise ProvisioningError(f"Existing Bucket {bucket_id} is not the expected private resource.")
    if bucket is None:
        if space is not None:
            raise ProvisioningError("The assistant Space exists without its private Bucket; no changes were made.")
        return (
            AssistantDiscovery(
                state=AssistantDiscoveryState.ABSENT,
                space_id=space_id,
                bucket_id=bucket_id,
                dockerfile_missing=False,
            ),
            None,
        )
    if space is None:
        return (
            AssistantDiscovery(
                state=AssistantDiscoveryState.BUCKET_ONLY,
                space_id=space_id,
                bucket_id=bucket_id,
                dockerfile_missing=False,
            ),
            None,
        )
    if space.id != space_id or space.author != username or space.private is not True or space.sdk != "docker":
        raise ProvisioningError(f"Existing Space {space_id} is not the expected private Docker resource.")
    if space.sha is None:
        raise ProvisioningError(f"Existing Space {space_id} has no readable revision.")

    if space.runtime is None or space.runtime.volumes is None:
        raise ProvisioningError(f"Existing Space {space_id} has no readable volume configuration.")
    expected_volume = Volume(
        type="bucket",
        source=bucket_id,
        mount_path=STATE_MOUNT_PATH,
        read_only=False,
    )
    if [volume.to_dict() for volume in space.runtime.volumes] != [expected_volume.to_dict()]:
        raise ProvisioningError(f"Existing Space {space_id} has an unexpected volume configuration.")
    if set(api.get_space_secrets(space_id)) != {"HF_TOKEN", ASSISTANT_API_TOKEN_ENV}:
        raise ProvisioningError(f"Existing Space {space_id} has an unexpected secret configuration.")

    try:
        dockerfile_path = api.hf_hub_download(
            space_id,
            "Dockerfile",
            repo_type="space",
            revision=space.sha,
        )
    except RemoteEntryNotFoundError:
        dockerfile_missing = True
    else:
        if not isinstance(dockerfile_path, str):
            raise ProvisioningError(f"Existing Space {space_id} is not managed by this provisioner.")
        dockerfile = Path(dockerfile_path).read_bytes()
        if dockerfile != ASSISTANT_DOCKERFILE:
            raise ProvisioningError(f"Existing Space {space_id} is not managed by this provisioner.")
        dockerfile_missing = False

    return (
        AssistantDiscovery(
            state=AssistantDiscoveryState.MANAGED,
            space_id=space_id,
            bucket_id=bucket_id,
            dockerfile_missing=dockerfile_missing,
        ),
        space.sha,
    )


def provision_assistant(
    hf_token: str,
    api_token: str,
    *,
    timeout: float = DEFAULT_PROVISIONING_TIMEOUT,
) -> ProvisionedAssistant:
    """Provision the signed-in user's canonical assistant resources."""
    if not _is_visible_ascii(hf_token, 1):
        raise ProvisioningError("A valid Hugging Face credential is required.")
    if not _is_visible_ascii(api_token, MIN_API_TOKEN_CHARS):
        raise ProvisioningError(
            f"{ASSISTANT_API_TOKEN_ENV} must contain {MIN_API_TOKEN_CHARS}–{MAX_TOKEN_CHARS} visible ASCII characters"
        )
    if not isfinite(timeout) or timeout <= 0:
        raise ProvisioningError("The provisioning timeout must be greater than zero.")

    api = HfApi(token=hf_token)
    discovery, space_revision = _inspect_assistant(api)
    expected_volume = Volume(
        type="bucket",
        source=discovery.bucket_id,
        mount_path=STATE_MOUNT_PATH,
        read_only=False,
    )
    if discovery.state == AssistantDiscoveryState.ABSENT:
        api.create_bucket(discovery.bucket_id, private=True, exist_ok=False)
        if not api.bucket_info(discovery.bucket_id).private:
            raise ProvisioningError(f"Hugging Face created {discovery.bucket_id} without private visibility.")
    if discovery.state in {AssistantDiscoveryState.ABSENT, AssistantDiscoveryState.BUCKET_ONLY}:
        api.create_repo(
            discovery.space_id,
            repo_type="space",
            space_sdk="docker",
            private=True,
            exist_ok=False,
            space_secrets=[
                {"key": "HF_TOKEN", "value": hf_token},
                {"key": ASSISTANT_API_TOKEN_ENV, "value": api_token},
            ],
            space_volumes=[expected_volume],
        )
        if api.space_info(discovery.space_id).private is not True:
            raise ProvisioningError(f"Hugging Face created {discovery.space_id} without private visibility.")
        api.upload_file(
            path_or_fileobj=ASSISTANT_DOCKERFILE,
            path_in_repo="Dockerfile",
            repo_id=discovery.space_id,
            repo_type="space",
            commit_message="Configure assistant runtime",
        )
    else:
        if discovery.dockerfile_missing:
            assert space_revision is not None
            api.upload_file(
                path_or_fileobj=ASSISTANT_DOCKERFILE,
                path_in_repo="Dockerfile",
                repo_id=discovery.space_id,
                repo_type="space",
                commit_message="Configure assistant runtime",
                parent_commit=space_revision,
            )
        api.add_space_secret(discovery.space_id, "HF_TOKEN", hf_token)
        api.add_space_secret(discovery.space_id, ASSISTANT_API_TOKEN_ENV, api_token)
        api.restart_space(discovery.space_id)

    runtime = api.wait_for_space(discovery.space_id, timeout=timeout)
    if runtime.stage != SpaceStage.RUNNING:
        raise ProvisioningError(f"The assistant Space stopped in the {runtime.stage} stage.")

    running_space = api.space_info(discovery.space_id)
    host = running_space.host
    if running_space.private is not True or not host:
        raise ProvisioningError("The assistant Space did not expose an API endpoint.")
    api_url = host if host.startswith("https://") else f"https://{host}"
    parsed_url = urlparse(api_url)
    if parsed_url.scheme != "https" or parsed_url.hostname is None or not parsed_url.hostname.endswith(".hf.space"):
        raise ProvisioningError("Hugging Face returned an invalid assistant endpoint.")

    return ProvisionedAssistant(
        space_id=discovery.space_id,
        bucket_id=discovery.bucket_id,
        api_url=api_url.rstrip("/"),
    )


def run_provisioning_command(input_stream: TextIO, output_stream: TextIO) -> None:
    """Provision an assistant and write non-secret metadata."""
    if input_stream.isatty():
        raise ProvisioningRequestError("Provisioning input must come from a trusted client process.")
    document = input_stream.read(MAX_PROVISIONING_REQUEST_CHARS + 1)
    if not document or len(document) > MAX_PROVISIONING_REQUEST_CHARS:
        raise ProvisioningRequestError("The provisioning request is empty or too large.")
    try:
        request: object = json.loads(document)
    except json.JSONDecodeError as exc:
        raise ProvisioningRequestError("The provisioning request is not valid JSON.") from exc
    if not isinstance(request, dict) or set(request) != {"hf_token", "api_token"}:
        raise ProvisioningRequestError("The provisioning request has an invalid shape.")
    hf_token = request["hf_token"]
    api_token = request["api_token"]
    if not isinstance(hf_token, str) or not isinstance(api_token, str):
        raise ProvisioningRequestError("The provisioning request contains invalid credentials.")
    try:
        provisioned = provision_assistant(hf_token, api_token)
        payload = {
            "space_id": provisioned.space_id,
            "bucket_id": provisioned.bucket_id,
            "api_url": provisioned.api_url,
        }
    except HfHubHTTPError as exc:
        raise ProvisioningError("Hugging Face could not inspect or provision the assistant.") from exc
    json.dump(payload, output_stream, separators=(",", ":"))
    output_stream.write("\n")


def main() -> int:
    """Provision a private Hugging Face assistant service."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    try:
        run_provisioning_command(sys.stdin, sys.stdout)
    except (ProvisioningError, ProvisioningRequestError, OSError) as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        logger.error("Cancelled.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
