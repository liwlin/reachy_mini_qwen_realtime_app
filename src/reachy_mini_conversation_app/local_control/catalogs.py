"""Browser-safe catalog definitions for local mobile control."""

import re
from typing import Literal
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urlsplit


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_SAFE_REPOSITORY_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_LOCAL_UI_HOSTS = frozenset({"0.0.0.0", "127.0.0.1", "localhost", "::"})


@dataclass(frozen=True)
class MotionSourceDefinition:
    """Describe one fixed recorded-move source exposed to the browser."""

    source_id: str
    dataset: str
    category: Literal["emotion", "dance"]
    label: str
    expected_names: tuple[str, ...] = ()


MUSIC_DANCE_NAMES: tuple[str, ...] = (
    "beyonce-single-ladies",
    "demon-hunters-1",
    "eagles-hotel-california",
    "eminem-lose-yourself",
    "feel-the-magic-in-the-air",
    "katy-perry-fireworks",
    "las-ketchup",
    "michael-jackson-thriller",
    "paint-it-black",
    "pharrell-williams-happy",
    "queen-we-will-rock-you",
    "spice-girls",
    "the-fratellis-whistle-for-the-choir",
    "the-white-stripes-seven-nation-army",
)


MOTION_SOURCES: dict[str, MotionSourceDefinition] = {
    "emotion": MotionSourceDefinition(
        source_id="emotion",
        dataset="pollen-robotics/reachy-mini-emotions-library",
        category="emotion",
        label="表情",
    ),
    "pollen_dance": MotionSourceDefinition(
        source_id="pollen_dance",
        dataset="pollen-robotics/reachy-mini-dances-library",
        category="dance",
        label="官方舞蹈",
    ),
    "music_dance": MotionSourceDefinition(
        source_id="music_dance",
        dataset="Anne-Charlotte/music",
        category="dance",
        label="音乐舞蹈",
        expected_names=MUSIC_DANCE_NAMES,
    ),
}


_EMOTION_DISPLAY: dict[str, tuple[str, str]] = {
    "understanding": ("🤝", "理解"),
    "scared": ("😨", "害怕"),
    "displeased": ("😒", "不悦"),
    "sad": ("😢", "难过"),
    "curious": ("🧐", "好奇"),
    "dance": ("🪩", "起舞"),
    "yes_sad": ("🥺", "伤心地点头"),
    "shy": ("😊", "害羞"),
    "resigned": ("😔", "无奈"),
    "relief": ("😌", "释然"),
    "dying": ("💀", "奄奄一息"),
    "go_away": ("👋", "请离开"),
    "attentive": ("👀", "专注"),
    "exhausted": ("😩", "筋疲力尽"),
    "reprimand": ("☝️", "责备"),
    "come": ("🫴", "过来"),
    "surprised": ("😲", "惊讶"),
    "indifferent": ("😐", "冷淡"),
    "thoughtful": ("🤔", "思考"),
    "laughing": ("😂", "大笑"),
    "inquiring": ("❓", "询问"),
    "fear": ("😱", "恐惧"),
    "impatient": ("⏳", "不耐烦"),
    "contempt": ("😏", "轻蔑"),
    "helpful": ("🤝", "乐于帮助"),
    "success": ("🎉", "成功"),
    "uncomfortable": ("😬", "不舒服"),
    "lost": ("😵‍💫", "迷茫"),
    "frustrated": ("😣", "沮丧"),
    "boredom": ("🥱", "无聊"),
    "grateful": ("🙏", "感谢"),
    "proud": ("😌", "自豪"),
    "confused": ("😕", "困惑"),
    "irritated": ("😤", "恼火"),
    "welcoming": ("👋", "欢迎"),
    "no_sad": ("🙅", "伤心地拒绝"),
    "no": ("🙅", "拒绝"),
    "cheerful": ("😄", "开心"),
    "amazed": ("🤩", "赞叹"),
    "disgusted": ("🤢", "厌恶"),
    "uncertain": ("🤷", "不确定"),
    "anxiety": ("😰", "焦虑"),
    "oops": ("😅", "糟糕"),
    "sleep": ("😴", "困倦"),
    "serenity": ("🧘", "平静"),
    "calming": ("🌿", "安抚"),
    "electric": ("⚡", "触电"),
    "yes": ("👍", "赞同"),
    "loving": ("🥰", "喜爱"),
    "incomprehensible": ("🤯", "无法理解"),
    "enthusiastic": ("🤗", "热情"),
    "rage": ("😡", "愤怒"),
    "tired": ("🥱", "疲惫"),
    "lonely": ("😞", "孤独"),
    "furious": ("🤬", "暴怒"),
    "downcast": ("😔", "低落"),
    "no_excited": ("🙅‍♂️", "兴奋地拒绝"),
}


_POLLEN_DANCE_DISPLAY: dict[str, tuple[str, str]] = {
    "simple_nod": ("🙂", "轻轻点头"),
    "head_tilt_roll": ("🎵", "侧头摇摆"),
    "side_to_side_sway": ("↔️", "左右摇摆"),
    "dizzy_spin": ("😵‍💫", "眩晕旋转"),
    "stumble_and_recover": ("😅", "踉跄恢复"),
    "headbanger_combo": ("🤘", "甩头组合"),
    "interwoven_spirals": ("🌀", "交织螺旋"),
    "sharp_side_tilt": ("📐", "快速侧倾"),
    "side_peekaboo": ("🙈", "侧身躲猫猫"),
    "yeah_nod": ("👍", "赞同点头"),
    "uh_huh_tilt": ("😌", "嗯哼侧倾"),
    "neck_recoil": ("⚡", "颈部后缩"),
    "chin_lead": ("🕺", "下巴领舞"),
    "groovy_sway_and_roll": ("🪩", "律动摇摆"),
    "chicken_peck": ("🐔", "小鸡啄食"),
    "side_glance_flick": ("👀", "快速侧瞥"),
    "polyrhythm_combo": ("🥁", "复合节拍"),
    "grid_snap": ("🤖", "机械格点"),
    "pendulum_swing": ("🕰️", "钟摆摇动"),
    "jackson_square": ("⬜", "杰克逊方步"),
}


_MUSIC_DANCE_DISPLAY: dict[str, tuple[str, str]] = {
    "beyonce-single-ladies": ("💍", "碧昂丝《单身女郎》"),
    "demon-hunters-1": ("👹", "恶魔猎人"),
    "eagles-hotel-california": ("🌴", "老鹰乐队《加州旅馆》"),
    "eminem-lose-yourself": ("🎤", "埃米纳姆《迷失自我》"),
    "feel-the-magic-in-the-air": ("✨", "《感受空气中的魔力》"),
    "katy-perry-fireworks": ("🎆", "凯蒂·佩里《烟火》"),
    "las-ketchup": ("🍅", "番茄姐妹舞"),
    "michael-jackson-thriller": ("🧟", "迈克尔·杰克逊《颤栗》"),
    "paint-it-black": ("🖤", "《漆成黑色》"),
    "pharrell-williams-happy": ("😀", "法瑞尔·威廉姆斯《快乐》"),
    "queen-we-will-rock-you": ("👑", "皇后乐队《我们将震撼你》"),
    "spice-girls": ("🎀", "辣妹组合"),
    "the-fratellis-whistle-for-the-choir": ("🎻", "法泰利乐队《为合唱团吹口哨》"),
    "the-white-stripes-seven-nation-army": ("⚔️", "白色条纹《七国军队》"),
}


def humanize_move_name(name: str) -> str:
    """Create a readable label without altering the raw playback identifier."""
    separated = re.sub(r"[-_]+", " ", name).strip()
    return re.sub(r"(?<=\D)(\d+)$", r" \1", separated)


def motion_display(source_id: str, name: str) -> dict[str, str]:
    """Return emoji and Chinese display text while preserving the playback ID."""
    display: tuple[str, str] | None = None
    if source_id == "emotion":
        match = re.fullmatch(r"(.+?)(\d+)?", name)
        stem = match.group(1).rstrip("_") if match else name
        variant = match.group(2) if match else None
        display = _EMOTION_DISPLAY.get(stem)
        if display is not None and variant is not None:
            display = (display[0], f"{display[1]} {variant}")
    elif source_id == "pollen_dance":
        display = _POLLEN_DANCE_DISPLAY.get(name)
    elif source_id == "music_dance":
        display = _MUSIC_DANCE_DISPLAY.get(name)

    emoji, label = display or ("🎭", f"动作：{humanize_move_name(name)}")
    return {"name": name, "label": label, "emoji": emoji}


def hf_dataset_cache_path(repo_id: str, cache_root: Path) -> Path:
    """Return the standard Hugging Face cache directory for one dataset ID."""
    segments = repo_id.split("/")
    if len(segments) != 2 or any(
        segment in {"", ".", ".."} or _SAFE_REPOSITORY_SEGMENT.fullmatch(segment) is None for segment in segments
    ):
        raise ValueError("invalid_dataset_id")
    return cache_root / f"datasets--{segments[0]}--{segments[1]}"


def sanitize_installed_app(raw: dict[str, object], current_name: str | None) -> dict[str, object]:
    """Return only display and local-navigation metadata for an installed app."""
    name = raw.get("name")
    if not isinstance(name, str) or _SAFE_IDENTIFIER.fullmatch(name) is None:
        raise ValueError("invalid_app_catalog_entry")

    extra = raw.get("extra")
    extra_mapping = extra if isinstance(extra, dict) else {}
    card_data = extra_mapping.get("cardData")
    card_mapping = card_data if isinstance(card_data, dict) else {}

    title = card_mapping.get("title")
    if not isinstance(title, str) or not title.strip():
        title = humanize_move_name(name).title()
    emoji = card_mapping.get("emoji")
    if not isinstance(emoji, str) or not emoji.strip():
        emoji = "📦"

    result: dict[str, object] = {
        "name": name,
        "title": title.strip(),
        "emoji": emoji.strip(),
        "active": name == current_name,
    }
    custom_url = extra_mapping.get("custom_app_url")
    if isinstance(custom_url, str):
        parsed = urlsplit(custom_url)
        try:
            port = parsed.port
        except ValueError:
            port = None
        if parsed.scheme in {"http", "https"} and parsed.hostname in _LOCAL_UI_HOSTS and port is not None:
            result["custom_ui_port"] = port
    return result
