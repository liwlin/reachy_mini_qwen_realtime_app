"""Tests for private resources created by the bundled provisioner."""

import io
import sys
import json
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from huggingface_hub import Volume
from huggingface_hub.errors import BucketNotFoundError, RepositoryNotFoundError, RemoteEntryNotFoundError

from reachy_mini_conversation_app.companion.provisioner import (
    STATE_MOUNT_PATH,
    ASSISTANT_DOCKERFILE,
    ProvisioningError,
    ProvisionedAssistant,
    main,
    provision_assistant,
)


SPACE_ID = "alice/smolagents-assistant-reachy-mini"
BUCKET_ID = "alice/smolagents-assistant-reachy-mini-data"
API_URL = "https://alice-smolagents-assistant-reachy-mini.hf.space"
API_TOKEN = "a" * 32
HF_TOKEN = "hf_oauth-token_123"


def _not_found_response() -> httpx.Response:
    return httpx.Response(404, request=httpx.Request("GET", "https://huggingface.co/api/test"))


def _expected_volume() -> Volume:
    return Volume(
        type="bucket",
        source=BUCKET_ID,
        mount_path=STATE_MOUNT_PATH,
        read_only=False,
    )


def _configure_managed_assistant(api: MagicMock, dockerfile: Path) -> None:
    dockerfile.write_bytes(ASSISTANT_DOCKERFILE)
    api.whoami.return_value = {"name": "alice"}
    api.bucket_info.return_value = SimpleNamespace(id=BUCKET_ID, private=True)
    api.space_info.return_value = SimpleNamespace(
        id=SPACE_ID,
        author="alice",
        private=True,
        sdk="docker",
        sha="space-revision",
        runtime=SimpleNamespace(volumes=[_expected_volume()]),
    )
    api.hf_hub_download.return_value = str(dockerfile)
    api.get_space_secrets.return_value = {
        "HF_TOKEN": SimpleNamespace(),
        "SMOL_ASSISTANT_API_TOKEN": SimpleNamespace(),
    }


@patch("reachy_mini_conversation_app.companion.provisioner.provision_assistant")
def test_command_provisions_without_exposing_credentials(
    provision: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Provisioning keeps credentials off stdout."""
    provision.return_value = ProvisionedAssistant(
        space_id=SPACE_ID,
        bucket_id=BUCKET_ID,
        api_url=API_URL,
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"hf_token": HF_TOKEN, "api_token": API_TOKEN})),
    )

    assert main() == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "space_id": SPACE_ID,
        "bucket_id": BUCKET_ID,
        "api_url": API_URL,
    }
    assert captured.err == ""
    assert HF_TOKEN not in captured.out
    assert API_TOKEN not in captured.out
    provision.assert_called_once_with(HF_TOKEN, API_TOKEN)


@patch("reachy_mini_conversation_app.companion.provisioner.HfApi")
def test_provision_assistant_creates_private_resources(api_class: MagicMock) -> None:
    """A clean account receives the current private, persistent runtime."""
    api = api_class.return_value
    api.whoami.return_value = {"name": "alice"}
    api.bucket_info.side_effect = [
        BucketNotFoundError("missing", response=_not_found_response()),
        SimpleNamespace(private=True),
    ]
    api.space_info.side_effect = [
        RepositoryNotFoundError("missing", response=_not_found_response()),
        SimpleNamespace(private=True),
        SimpleNamespace(private=True, host=API_URL),
    ]
    api.wait_for_space.return_value = SimpleNamespace(stage="RUNNING")

    provisioned = provision_assistant("hf_oauth_token", API_TOKEN)

    assert ASSISTANT_DOCKERFILE.startswith(
        b"FROM ghcr.io/alozowski/smolagents-assistant@"
        b"sha256:d04e612bc928398a320bc632de88c9927994cf24a508226e49a574ee216440bf\n"
    )
    api.create_bucket.assert_called_once_with(BUCKET_ID, private=True, exist_ok=False)
    api.create_repo.assert_called_once_with(
        SPACE_ID,
        repo_type="space",
        space_sdk="docker",
        private=True,
        exist_ok=False,
        space_secrets=[
            {"key": "HF_TOKEN", "value": "hf_oauth_token"},
            {"key": "SMOL_ASSISTANT_API_TOKEN", "value": API_TOKEN},
        ],
        space_volumes=[_expected_volume()],
    )
    api.upload_file.assert_called_once_with(
        path_or_fileobj=ASSISTANT_DOCKERFILE,
        path_in_repo="Dockerfile",
        repo_id=SPACE_ID,
        repo_type="space",
        commit_message="Configure assistant runtime",
    )
    assert provisioned.space_id == SPACE_ID
    assert provisioned.bucket_id == BUCKET_ID
    assert provisioned.api_url == API_URL


@patch("reachy_mini_conversation_app.companion.provisioner.HfApi")
def test_provision_assistant_recreates_space_over_existing_bucket(api_class: MagicMock) -> None:
    """Deleting the Space preserves and remounts the existing Bucket."""
    api = api_class.return_value
    api.whoami.return_value = {"name": "alice"}
    api.bucket_info.return_value = SimpleNamespace(id=BUCKET_ID, private=True)
    api.space_info.side_effect = [
        RepositoryNotFoundError("missing", response=_not_found_response()),
        SimpleNamespace(private=True),
        SimpleNamespace(private=True, host=API_URL),
    ]
    api.wait_for_space.return_value = SimpleNamespace(stage="RUNNING")

    provisioned = provision_assistant("hf_oauth_token", API_TOKEN)

    api.create_bucket.assert_not_called()
    api.create_repo.assert_called_once()
    assert api.create_repo.call_args.kwargs["space_volumes"] == [_expected_volume()]
    api.upload_file.assert_called_once_with(
        path_or_fileobj=ASSISTANT_DOCKERFILE,
        path_in_repo="Dockerfile",
        repo_id=SPACE_ID,
        repo_type="space",
        commit_message="Configure assistant runtime",
    )
    assert provisioned.bucket_id == BUCKET_ID


@patch("reachy_mini_conversation_app.companion.provisioner.HfApi")
def test_provision_assistant_finishes_interrupted_setup(api_class: MagicMock, tmp_path: Path) -> None:
    """Retrying setup uploads the missing runtime to the same resources."""
    api = api_class.return_value
    dockerfile = tmp_path / "Dockerfile"
    _configure_managed_assistant(api, dockerfile)
    api.hf_hub_download.side_effect = RemoteEntryNotFoundError("missing", response=_not_found_response())
    api.space_info.side_effect = [
        api.space_info.return_value,
        SimpleNamespace(private=True, host=API_URL),
    ]
    api.wait_for_space.return_value = SimpleNamespace(stage="RUNNING")

    provision_assistant("hf_oauth_token", API_TOKEN)

    api.create_bucket.assert_not_called()
    api.create_repo.assert_not_called()
    api.upload_file.assert_called_once_with(
        path_or_fileobj=ASSISTANT_DOCKERFILE,
        path_in_repo="Dockerfile",
        repo_id=SPACE_ID,
        repo_type="space",
        commit_message="Configure assistant runtime",
        parent_commit="space-revision",
    )
    api.add_space_secret.assert_any_call(SPACE_ID, "HF_TOKEN", "hf_oauth_token")
    api.add_space_secret.assert_any_call(SPACE_ID, "SMOL_ASSISTANT_API_TOKEN", API_TOKEN)
    api.restart_space.assert_called_once_with(SPACE_ID)


@pytest.mark.parametrize(
    "problem",
    ["public_bucket", "public_space", "space_only", "dockerfile", "volume", "secrets"],
)
@patch("reachy_mini_conversation_app.companion.provisioner.HfApi")
def test_provision_assistant_rejects_non_exact_resources(
    api_class: MagicMock,
    problem: str,
    tmp_path: Path,
) -> None:
    """Only an exact private managed pair can be reconnected."""
    api = api_class.return_value
    dockerfile = tmp_path / "Dockerfile"
    _configure_managed_assistant(api, dockerfile)
    if problem == "public_bucket":
        api.bucket_info.return_value = SimpleNamespace(id=BUCKET_ID, private=False)
    elif problem == "public_space":
        api.space_info.return_value.private = False
    elif problem == "space_only":
        api.bucket_info.side_effect = BucketNotFoundError("missing", response=_not_found_response())
    elif problem == "dockerfile":
        dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    elif problem == "volume":
        api.space_info.return_value.runtime.volumes = []
    else:
        api.get_space_secrets.return_value = {"HF_TOKEN": SimpleNamespace()}

    with pytest.raises(ProvisioningError):
        provision_assistant("hf_oauth_token", API_TOKEN)

    api.create_bucket.assert_not_called()
    api.create_repo.assert_not_called()
    api.upload_file.assert_not_called()
    api.add_space_secret.assert_not_called()
    api.restart_space.assert_not_called()
