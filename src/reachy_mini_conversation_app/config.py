import os
import re
import sys
import logging
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit
from importlib.resources import files

from dotenv import find_dotenv, load_dotenv


# Locked profile: set to a profile name (e.g., "astronomer") to lock the app
# to that profile and disable all profile switching. Leave as None for normal behavior.
LOCKED_PROFILE: str | None = None
PROJECT_ROOT = Path(__file__).parents[2].resolve()


def _is_source_checkout_root(root: Path) -> bool:
    """Return whether the given root looks like this project's source checkout."""
    return (root / "pyproject.toml").is_file() and (root / "src" / "reachy_mini_conversation_app").is_dir()


def _packaged_profiles_directory() -> Path | None:
    """Return the installed wheel's packaged profiles directory when available."""
    try:
        return Path(str(files("reachy_talk_data").joinpath("profiles")))
    except Exception:
        return None


def _resolve_default_profiles_directory() -> Path:
    """Resolve built-in profiles from source checkout or installed package data."""
    source_profiles = PROJECT_ROOT / "profiles"
    if _is_source_checkout_root(PROJECT_ROOT) and source_profiles.is_dir():
        return source_profiles

    packaged_profiles = _packaged_profiles_directory()
    if packaged_profiles is not None and packaged_profiles.is_dir():
        return packaged_profiles

    return source_profiles


DEFAULT_PROFILES_DIRECTORY = _resolve_default_profiles_directory()

USER_PERSONALITIES_DIRNAME = "user_personalities"
TERMINAL_USER_PERSONALITIES_DIRECTORY = Path("external_content") / USER_PERSONALITIES_DIRNAME

# Qwen3-TTS CustomVoice speaker catalog from the deployed Hugging Face backend.
HF_AVAILABLE_VOICES: list[str] = [
    "Aiden",
    "Ryan",
    "Dylan",
    "Eric",
    "Ono_Anna",
    "Serena",
    "Sohee",
    "Uncle_Fu",
    "Vivian",
]

HF_BACKEND = "huggingface"
QWEN_BACKEND = "qwen"
REALTIME_BACKEND_ENV = "REALTIME_BACKEND"
QWEN_AVAILABLE_VOICES = ["Tina", "Cherry", "Serena", "Ethan", "Chelsie"]
QWEN_REALTIME_REGIONS = {"cn-beijing", "ap-southeast-1"}
HF_REALTIME_CONNECTION_MODE_ENV = "HF_REALTIME_CONNECTION_MODE"
HF_REALTIME_WS_URL_ENV = "HF_REALTIME_WS_URL"
REALTIME_TRANSCRIPTION_LANGUAGE_ENV = "REALTIME_TRANSCRIPTION_LANGUAGE"
HF_LOCAL_CONNECTION_MODE = "local"
HF_DEPLOYED_CONNECTION_MODE = "deployed"
HF_REALTIME_SESSION_PROXY_URL = "https://pollen-robotics-reachy-mini-realtime-url.hf.space/session"


@dataclass(frozen=True)
class HFBackendDefaults:
    """Defaults for the Hugging Face realtime backend."""

    connection_mode: str = HF_DEPLOYED_CONNECTION_MODE
    # App-managed Hugging Face Space proxy. The Space forwards to the current
    # session allocator, so allocator changes do not require app releases.
    # Users who need a custom target should use HF_REALTIME_CONNECTION_MODE=local
    # with HF_REALTIME_WS_URL.
    session_url: str = HF_REALTIME_SESSION_PROXY_URL
    voice: str = "Aiden"
    direct_port: int = 8765


HF_DEFAULTS = HFBackendDefaults()

logger = logging.getLogger(__name__)

# Removed backend selectors kept in stale robot .env files: warn but ignore them.
_OBSOLETE_BACKEND_ENV_NAMES = ("BACKEND_PROVIDER", "MODEL_NAME")


def _legacy_qwen_backend_requested() -> bool:
    """Return whether a v0.5 environment selected Qwen."""
    provider = (os.getenv("BACKEND_PROVIDER") or "").strip().lower()
    model = (os.getenv("MODEL_NAME") or "").strip().lower()
    return provider == QWEN_BACKEND or model.startswith("qwen")


def _realtime_backend_from_env() -> str:
    """Resolve the v1 backend, migrating the supported v0.5 Qwen selector."""
    configured = (os.getenv(REALTIME_BACKEND_ENV) or "").strip().lower()
    if configured:
        return configured
    return QWEN_BACKEND if _legacy_qwen_backend_requested() else HF_BACKEND


def _qwen_model_from_env() -> str:
    """Resolve the Qwen model while retaining a v0.5 MODEL_NAME override."""
    configured = (os.getenv("QWEN_MODEL_NAME") or "").strip()
    if configured:
        return configured
    legacy_model = (os.getenv("MODEL_NAME") or "").strip()
    if _legacy_qwen_backend_requested() and legacy_model.lower().startswith("qwen"):
        return legacy_model
    return "qwen3.5-omni-flash-realtime"


def _warn_on_obsolete_backend_env() -> None:
    """Warn when old backend selectors are migrated or ignored."""
    present = [name for name in _OBSOLETE_BACKEND_ENV_NAMES if (os.getenv(name) or "").strip()]
    if present and _legacy_qwen_backend_requested() and not (os.getenv(REALTIME_BACKEND_ENV) or "").strip():
        logger.warning(
            "Migrating legacy Qwen backend environment variable(s): %s. Prefer REALTIME_BACKEND=qwen and "
            "QWEN_MODEL_NAME for future configuration.",
            ", ".join(present),
        )
    elif present:
        logger.warning(
            "Ignoring obsolete backend environment variable(s): %s. This app uses the Hugging Face backend only "
            "unless REALTIME_BACKEND=qwen is selected.",
            ", ".join(present),
        )


def _env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean environment flag.

    Accepted truthy values: 1, true, yes, on
    Accepted falsy values: 0, false, no, off
    """
    raw = os.getenv(name)
    if raw is None:
        return default

    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False

    logger.warning("Invalid boolean value for %s=%r, using default=%s", name, raw, default)
    return default


APP_TIMEOUT_MINUTES_ENV = "REACHY_MINI_APP_TIMEOUT_MINUTES"
DEFAULT_APP_TIMEOUT_MINUTES = 1440.0


def resolve_app_timeout_minutes() -> float | None:
    """Read the app inactivity timeout (minutes) from the environment; None means disabled."""
    raw_value = os.getenv(APP_TIMEOUT_MINUTES_ENV, "").strip()
    if not raw_value:
        return DEFAULT_APP_TIMEOUT_MINUTES
    try:
        timeout_minutes = float(raw_value)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; using default.", APP_TIMEOUT_MINUTES_ENV, raw_value)
        return DEFAULT_APP_TIMEOUT_MINUTES
    return timeout_minutes if timeout_minutes > 0 else None


def _normalize_hf_connection_mode(value: str | None) -> str | None:
    """Normalize the Hugging Face connection mode, if explicitly configured."""
    candidate = (value or "").strip().lower()
    if not candidate:
        return None

    if candidate not in {HF_LOCAL_CONNECTION_MODE, HF_DEPLOYED_CONNECTION_MODE}:
        logger.warning(
            "Invalid %s=%r. Expected local or deployed.",
            HF_REALTIME_CONNECTION_MODE_ENV,
            value,
        )
        return None
    return candidate


def _normalize_transcription_language(value: str | None) -> str:
    """Return the configured realtime transcription language."""
    candidate = (value or "").strip()
    return candidate or "en"


@dataclass(frozen=True)
class HFConnectionSelection:
    """Resolved Hugging Face connection mode and target availability."""

    mode: str
    has_target: bool
    session_url: str | None = None
    direct_ws_url: str | None = None


@dataclass(frozen=True)
class HFRealtimeURLParts:
    """Parsed Hugging Face realtime URL components used by UI and client setup."""

    base_url: str
    websocket_base_url: str
    connect_query: dict[str, str]
    host: str | None
    port: int | None
    has_realtime_path: bool


def parse_hf_realtime_url(realtime_url: str) -> HFRealtimeURLParts:
    """Parse a Hugging Face realtime URL into OpenAI-compatible client endpoints."""
    parsed = urlsplit(realtime_url)
    scheme = parsed.scheme.lower()
    if scheme not in {"ws", "wss", "http", "https"}:
        raise ValueError(
            "Expected Hugging Face realtime URL to start with ws://, wss://, http://, or https://, "
            f"got: {realtime_url}"
        )

    path = parsed.path.rstrip("/")
    has_realtime_path = path.endswith("/realtime")
    if has_realtime_path:
        base_path = path[: -len("/realtime")]
    else:
        base_path = path

    connect_query = {key: value for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "model"}
    http_scheme = "https" if scheme in {"wss", "https"} else "http"
    websocket_scheme = "wss" if scheme in {"wss", "https"} else "ws"
    base_url = urlunsplit((http_scheme, parsed.netloc, base_path, "", ""))
    websocket_base_url = urlunsplit((websocket_scheme, parsed.netloc, base_path, "", ""))
    return HFRealtimeURLParts(
        base_url=base_url,
        websocket_base_url=websocket_base_url,
        connect_query=connect_query,
        host=parsed.hostname,
        port=parsed.port or HF_DEFAULTS.direct_port,
        has_realtime_path=has_realtime_path,
    )


def parse_hf_direct_target(ws_url: str | None) -> tuple[str | None, int | None]:
    """Extract host and port from a direct Hugging Face realtime URL."""
    if not ws_url:
        return None, None
    try:
        parsed = parse_hf_realtime_url(ws_url)
        return parsed.host, parsed.port
    except Exception:
        return None, None


def build_hf_direct_ws_url(host: str, port: int) -> str:
    """Build the direct Hugging Face realtime websocket URL used by the app."""
    return f"ws://{host}:{port}/v1/realtime"


def _collect_profile_names(profiles_root: Path) -> set[str]:
    """Return declarative profile names from a profiles root directory."""
    if not profiles_root.exists() or not profiles_root.is_dir():
        return set()
    return {path.name for path in profiles_root.iterdir() if path.is_dir() and (path / "profile.md").is_file()}


def list_tool_module_names(tools_root: Path | None) -> list[str]:
    """Return valid importable tool module names from a directory."""
    if tools_root is None or not tools_root.is_dir():
        return []

    ignored = {"__init__", "core_tools"}
    tool_names: list[str] = []
    try:
        for tool_file in tools_root.glob("*.py"):
            if not tool_file.is_file() or tool_file.stem in ignored or tool_file.name.startswith("_"):
                continue
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tool_file.stem) is None:
                logger.warning("Skipping tool module with invalid name: %s", tool_file)
                continue
            tool_names.append(tool_file.stem)
    except OSError as exc:
        logger.warning("Failed to list tool modules in %s: %s", tools_root, exc)
    return sorted(tool_names)


def _raise_on_name_collisions(
    *,
    label: str,
    external_root: Path,
    internal_root: Path,
    external_names: set[str],
    internal_names: set[str],
) -> None:
    """Raise with a clear message when external/internal names collide."""
    collisions = sorted(external_names & internal_names)
    if not collisions:
        return

    raise RuntimeError(
        f"Config.__init__(): Ambiguous {label} names found in both external and built-in libraries: {collisions}. "
        f"External {label} root: {external_root}. Built-in {label} root: {internal_root}. "
        f"Please rename the conflicting external {label}(s) to continue."
    )


# Validate LOCKED_PROFILE at startup
if LOCKED_PROFILE is not None:
    _profiles_dir = DEFAULT_PROFILES_DIRECTORY
    _profile_path = _profiles_dir / LOCKED_PROFILE
    _profile_file = _profile_path / "profile.md"
    if not _profile_path.is_dir():
        logger.critical("LOCKED_PROFILE %r does not exist in %s", LOCKED_PROFILE, _profiles_dir)
        sys.exit(1)
    if not _profile_file.is_file():
        logger.critical("LOCKED_PROFILE %r has no profile definition", LOCKED_PROFILE)
        sys.exit(1)

_skip_dotenv = _env_flag("REACHY_MINI_SKIP_DOTENV", default=False)

if _skip_dotenv:
    logger.info("Skipping .env loading because REACHY_MINI_SKIP_DOTENV is set")
else:
    # Locate .env file (search upward from current working directory)
    dotenv_path = find_dotenv(usecwd=True)

    if dotenv_path:
        # Load .env and override environment variables
        load_dotenv(dotenv_path=dotenv_path, override=True)
        logger.info(f"Configuration loaded from {dotenv_path}")
    else:
        logger.warning("No .env file found, using environment variables")

_warn_on_obsolete_backend_env()


class Config:
    """Configuration class for the conversation app."""

    HF_REALTIME_CONNECTION_MODE = (
        _normalize_hf_connection_mode(os.getenv(HF_REALTIME_CONNECTION_MODE_ENV)) or HF_DEFAULTS.connection_mode
    )
    # Deliberately ignore HF_REALTIME_SESSION_URL from the environment; the app-managed proxy is HF_DEFAULTS.session_url.
    HF_REALTIME_SESSION_URL = HF_DEFAULTS.session_url
    HF_REALTIME_WS_URL = os.getenv(HF_REALTIME_WS_URL_ENV)
    REALTIME_TRANSCRIPTION_LANGUAGE = _normalize_transcription_language(os.getenv(REALTIME_TRANSCRIPTION_LANGUAGE_ENV))
    HF_TOKEN = os.getenv("HF_TOKEN")  # Optional, falls back to hf auth login if not set
    REALTIME_BACKEND = _realtime_backend_from_env()
    QWEN_API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    QWEN_REALTIME_URL = os.getenv("QWEN_REALTIME_URL")
    QWEN_WORKSPACE_ID = os.getenv("QWEN_WORKSPACE_ID")
    QWEN_REGION = os.getenv("QWEN_REGION", "cn-beijing")
    QWEN_MODEL_NAME = _qwen_model_from_env()

    logger.debug(
        "HF mode: %s, HF session URL set: %s, HF direct URL set: %s",
        HF_REALTIME_CONNECTION_MODE,
        bool(HF_REALTIME_SESSION_URL and HF_REALTIME_SESSION_URL.strip()),
        bool(HF_REALTIME_WS_URL and HF_REALTIME_WS_URL.strip()),
    )

    # Filesystem root containing profile directories, not a Python import path.
    _profiles_directory_env = os.getenv("REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY")
    PROFILES_DIRECTORY = Path(_profiles_directory_env) if _profiles_directory_env else DEFAULT_PROFILES_DIRECTORY
    INSTANCE_PATH: Path | None = None  # set at startup; writable home for UI-created profiles
    _tools_directory_env = os.getenv("REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY")
    TOOLS_DIRECTORY = Path(_tools_directory_env) if _tools_directory_env else None
    AUTOLOAD_EXTERNAL_TOOLS = _env_flag("AUTOLOAD_EXTERNAL_TOOLS", default=False)
    REACHY_MINI_CUSTOM_PROFILE = LOCKED_PROFILE or os.getenv("REACHY_MINI_CUSTOM_PROFILE")

    logger.debug(f"Custom Profile: {REACHY_MINI_CUSTOM_PROFILE}")

    def __init__(self) -> None:
        """Initialize the configuration."""
        if (
            self.REACHY_MINI_CUSTOM_PROFILE
            and self.REACHY_MINI_CUSTOM_PROFILE != "default"
            and self.PROFILES_DIRECTORY != DEFAULT_PROFILES_DIRECTORY
        ):
            selected_profile_path = self.PROFILES_DIRECTORY / self.REACHY_MINI_CUSTOM_PROFILE
            if not (selected_profile_path / "profile.md").is_file():
                available_profiles = sorted(_collect_profile_names(self.PROFILES_DIRECTORY))
                raise RuntimeError(
                    "Config.__init__(): Selected profile "
                    f"'{self.REACHY_MINI_CUSTOM_PROFILE}' was not found in external profiles root "
                    f"{self.PROFILES_DIRECTORY}. "
                    f"Available external profiles: {available_profiles}. "
                    "Either set 'REACHY_MINI_CUSTOM_PROFILE' to one of the available external profiles "
                    "or unset 'REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY' to use built-in profiles."
                )

        if self.PROFILES_DIRECTORY != DEFAULT_PROFILES_DIRECTORY:
            external_profiles = _collect_profile_names(self.PROFILES_DIRECTORY)
            internal_profiles = _collect_profile_names(DEFAULT_PROFILES_DIRECTORY)
            _raise_on_name_collisions(
                label="profile",
                external_root=self.PROFILES_DIRECTORY,
                internal_root=DEFAULT_PROFILES_DIRECTORY,
                external_names=external_profiles,
                internal_names=internal_profiles,
            )

        if self.TOOLS_DIRECTORY is not None:
            builtin_tools_root = Path(__file__).parent / "tools"
            external_tools = set(list_tool_module_names(self.TOOLS_DIRECTORY))
            internal_tools = set(list_tool_module_names(builtin_tools_root))
            _raise_on_name_collisions(
                label="tool",
                external_root=self.TOOLS_DIRECTORY,
                internal_root=builtin_tools_root,
                external_names=external_tools,
                internal_names=internal_tools,
            )

        if self.PROFILES_DIRECTORY != DEFAULT_PROFILES_DIRECTORY:
            logger.warning(
                "Environment variable 'REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY' is set. "
                "Profiles will be loaded from %s.",
                self.PROFILES_DIRECTORY,
            )
        else:
            logger.info(
                "'REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY' is not set. Using built-in profiles from %s.",
                DEFAULT_PROFILES_DIRECTORY,
            )

        if self.TOOLS_DIRECTORY is not None:
            logger.warning(
                "Environment variable 'REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY' is set. "
                "External tools will be loaded from %s.",
                self.TOOLS_DIRECTORY,
            )
        else:
            logger.info("'REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY' is not set. Using built-in shared tools only.")

    def user_personalities_root(self) -> Path:
        """Return the writable root for user-created profiles."""
        if self.INSTANCE_PATH is None:
            return TERMINAL_USER_PERSONALITIES_DIRECTORY
        return self.INSTANCE_PATH / USER_PERSONALITIES_DIRNAME

    def resolve_profile_dir(self, profile: str) -> Path:
        """On-disk directory for a profile selection."""
        head, _, tail = profile.partition("/")
        if head == USER_PERSONALITIES_DIRNAME and tail:
            return self.user_personalities_root() / tail
        return self.PROFILES_DIRECTORY / profile


config = Config()


def refresh_runtime_config_from_env() -> None:
    """Refresh mutable runtime config fields from the current environment."""
    _warn_on_obsolete_backend_env()
    config.HF_REALTIME_CONNECTION_MODE = (
        _normalize_hf_connection_mode(os.getenv(HF_REALTIME_CONNECTION_MODE_ENV)) or HF_DEFAULTS.connection_mode
    )
    # Deliberately ignore HF_REALTIME_SESSION_URL from the environment; the app-managed proxy is HF_DEFAULTS.session_url.
    config.HF_REALTIME_SESSION_URL = HF_DEFAULTS.session_url
    config.HF_REALTIME_WS_URL = os.getenv(HF_REALTIME_WS_URL_ENV)
    config.REALTIME_TRANSCRIPTION_LANGUAGE = _normalize_transcription_language(
        os.getenv(REALTIME_TRANSCRIPTION_LANGUAGE_ENV)
    )
    config.HF_TOKEN = os.getenv("HF_TOKEN")
    config.REALTIME_BACKEND = _realtime_backend_from_env()
    config.QWEN_API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    config.QWEN_REALTIME_URL = os.getenv("QWEN_REALTIME_URL")
    config.QWEN_WORKSPACE_ID = os.getenv("QWEN_WORKSPACE_ID")
    config.QWEN_REGION = os.getenv("QWEN_REGION", "cn-beijing")
    config.QWEN_MODEL_NAME = _qwen_model_from_env()
    config.REACHY_MINI_CUSTOM_PROFILE = LOCKED_PROFILE or os.getenv("REACHY_MINI_CUSTOM_PROFILE")


def get_available_voices() -> list[str]:
    """Return the curated voice list for the selected backend."""
    return list(QWEN_AVAILABLE_VOICES if get_realtime_backend() == QWEN_BACKEND else HF_AVAILABLE_VOICES)


def get_default_voice() -> str:
    """Return the default voice for the selected backend."""
    return "Tina" if get_realtime_backend() == QWEN_BACKEND else HF_DEFAULTS.voice


def get_realtime_backend() -> str:
    """Return the selected realtime provider, preserving Hugging Face as the default."""
    backend = (getattr(config, "REALTIME_BACKEND", None) or HF_BACKEND).strip().lower()
    if backend not in {HF_BACKEND, QWEN_BACKEND}:
        raise RuntimeError(f"{REALTIME_BACKEND_ENV} must be set to {HF_BACKEND} or {QWEN_BACKEND}.")
    return backend


def get_qwen_realtime_url() -> str | None:
    """Return the configured Qwen Realtime WebSocket endpoint."""
    model = (config.QWEN_MODEL_NAME or "qwen3.5-omni-flash-realtime").strip()
    configured_url = (config.QWEN_REALTIME_URL or "").strip()
    if configured_url:
        parts = urlsplit(configured_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.setdefault("model", model)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    workspace_id = (config.QWEN_WORKSPACE_ID or "").strip()
    region = (config.QWEN_REGION or "cn-beijing").strip()
    if not workspace_id or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", workspace_id):
        return None
    if region not in QWEN_REALTIME_REGIONS:
        return None
    return f"wss://{workspace_id}.{region}.maas.aliyuncs.com/api-ws/v1/realtime?{urlencode({'model': model})}"


def is_qwen_realtime_url_allowed(url: str | None) -> bool:
    """Return whether the URL is an official Alibaba Cloud Realtime endpoint."""
    if not url:
        return False
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        return False
    suffixes = tuple(f".{region}.maas.aliyuncs.com" for region in QWEN_REALTIME_REGIONS)
    return (
        parts.scheme == "wss"
        and parts.username is None
        and parts.password is None
        and port in {None, 443}
        and host.endswith(suffixes)
        and parts.path == "/api-ws/v1/realtime"
    )


def has_realtime_target() -> bool:
    """Return whether the selected backend has its required connection settings."""
    if get_realtime_backend() == QWEN_BACKEND:
        url = get_qwen_realtime_url()
        return bool((config.QWEN_API_KEY or "").strip() and is_qwen_realtime_url_allowed(url))
    return has_hf_realtime_target()


def get_hf_session_url() -> str | None:
    """Return the built-in Hugging Face session proxy URL, if any."""
    value = (getattr(config, "HF_REALTIME_SESSION_URL", None) or "").strip()
    return value or None


def get_hf_direct_ws_url() -> str | None:
    """Return the configured direct Hugging Face realtime URL, if any."""
    value = (getattr(config, "HF_REALTIME_WS_URL", None) or "").strip()
    return value or None


def get_hf_connection_selection() -> HFConnectionSelection:
    """Resolve the selected Hugging Face connection mode and whether it is usable."""
    session_url = get_hf_session_url()
    direct_ws_url = get_hf_direct_ws_url()
    mode = _normalize_hf_connection_mode(getattr(config, "HF_REALTIME_CONNECTION_MODE", None))
    if mode is None:
        raise RuntimeError(f"{HF_REALTIME_CONNECTION_MODE_ENV} must be set to local or deployed.")

    target = direct_ws_url if mode == HF_LOCAL_CONNECTION_MODE else session_url

    return HFConnectionSelection(
        mode=mode,
        has_target=bool(target),
        session_url=session_url,
        direct_ws_url=direct_ws_url,
    )


def has_hf_realtime_target() -> bool:
    """Return whether Hugging Face has a target for the selected mode."""
    return get_hf_connection_selection().has_target


def set_instance_path(instance_path: str | Path | None) -> None:
    """Record the app instance dir so UI-created profiles persist outside package data."""
    config.INSTANCE_PATH = Path(instance_path) if instance_path else None


def set_custom_profile(profile: str | None) -> None:
    """Update the selected profile in runtime config and the environment."""
    if LOCKED_PROFILE is not None:
        return
    if profile:
        os.environ["REACHY_MINI_CUSTOM_PROFILE"] = profile
    else:
        os.environ.pop("REACHY_MINI_CUSTOM_PROFILE", None)
    config.REACHY_MINI_CUSTOM_PROFILE = profile
