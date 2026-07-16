"""DAK.GG 文本解析。"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any


MAP_NAMES = {
    "Erangel",
    "Miramar",
    "Sanhok",
    "Vikendi",
    "Karakin",
    "Paramo",
    "Haven",
    "Taego",
    "Deston",
    "Rondo",
    "Tiger",
    "艾伦格",
    "米拉玛",
    "萨诺",
    "维寒迪",
    "卡拉金",
    "帕拉莫",
    "褐湾",
    "泰戈",
    "帝斯顿",
    "荣都",
    "老虎",
}

MODE_PATTERN = re.compile(
    r"\*{0,2}(Solo|Duo|Squad|1-Man Squad|单排|双排|四排)"
    r"\s*[_\(（]*\s*(Normal|Ranked|Casual|Competitive|Arcade|Event)?"
    r"\s*[_\)）]*\*{0,2}",
    re.IGNORECASE,
)
SECTION_PATTERN = re.compile(r"####\s*(?:매치\s*요약\s*정보|マッチ|Match|比赛)")
RELATIVE_TIME_PATTERN = re.compile(r"(\d+)\s*(h|d|m|min)\s*ago", re.IGNORECASE)
ABSOLUTE_TIME_PATTERN = re.compile(
    r"(?:(\d{1,2})\s+([A-Za-z]{3,9})|([A-Za-z]{3,9})\s+(\d{1,2}))"
    r"(?:[,\s]+(\d{4}))?"
)
MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

API_MAP_NAMES = {
    "Erangel_Main": "Erangel",
    "Baltic_Main": "Erangel",
    "Desert_Main": "Miramar",
    "Savage_Main": "Sanhok",
    "Range_Main": "Training Mode",
    "DihorOtok_Main": "Vikendi",
    "Summerland_Main": "Karakin",
    "Chimera_Main": "Paramo",
    "Heaven_Main": "Haven",
    "Tiger_Main": "Taego",
    "Kiki_Main": "Deston",
    "Neon_Main": "Rondo",
}

API_WEAPON_NAMES = {
    "WeapAUG_C": "AUG A3",
    "WeapBerylM762_C": "Beryl",
    "WeapDragunov_C": "Dragunov",
    "WeapHK416_C": "M416",
    "WeapMini14_C": "Mini 14",
    "WeapMP5K_C": "MP5K",
    "WeapUMP_C": "UMP45",
    "WeapWin94_C": "Win94",
    "WeapWinchester_C": "Win94",
}


def parse_time_label(text: str, scraped_at: datetime) -> tuple[datetime | None, str | None]:
    """解析相对或固定日期，返回时间及精度。"""
    normalized = text.strip()
    try:
        iso_time = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        iso_time = None
    if iso_time is not None:
        if iso_time.tzinfo is not None and scraped_at.tzinfo is not None:
            iso_time = iso_time.astimezone(scraped_at.tzinfo)
        return iso_time, "exact"

    relative = RELATIVE_TIME_PATTERN.search(normalized)
    if relative:
        value, unit = int(relative.group(1)), relative.group(2).lower()
        if unit in {"m", "min"}:
            return scraped_at - timedelta(minutes=value), "minute"
        if unit == "h":
            return scraped_at - timedelta(hours=value), "hour"
        return scraped_at - timedelta(days=value), "day"

    absolute = ABSOLUTE_TIME_PATTERN.fullmatch(normalized)
    if not absolute:
        return None, None
    day = int(absolute.group(1) or absolute.group(4))
    month_name = (absolute.group(2) or absolute.group(3)).lower()
    month = MONTHS.get(month_name)
    if not month:
        return None, None
    year = int(absolute.group(5) or scraped_at.year)
    candidate = scraped_at.replace(
        year=year,
        month=month,
        day=day,
        hour=12,
        minute=0,
        second=0,
        microsecond=0,
    )
    if absolute.group(5) is None and candidate > scraped_at + timedelta(days=1):
        candidate = candidate.replace(year=year - 1)
    return candidate, "date"


def parse_dakgg_markdown(
    text: str,
    player_alias: str,
    scraped_at: datetime,
    time_start: datetime,
    time_end: datetime,
    keep_modes: tuple[str, ...] | list[str] = ("Squad",),
    occurrence_counts: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """解析比赛，只返回时间明确落在目标时段内的指定模式比赛。"""
    matches: list[dict[str, Any]] = []
    occurrence_counts = occurrence_counts if occurrence_counts is not None else defaultdict(int)
    sections = SECTION_PATTERN.split(text)

    for section in sections[1:]:
        match_data = _parse_one_match(section.strip(), scraped_at)
        if match_data["placement"] is None:
            continue
        if match_data["map"] == "Training Mode":
            continue
        if match_data["mode"] not in keep_modes:
            continue
        approx_time = match_data.get("approx_time")
        if approx_time is None:
            continue
        if not time_start <= approx_time <= time_end:
            continue

        if match_data.get("match_id"):
            match_data["match_key"] = f"dakgg:{match_data['match_id']}"
        else:
            base_key = _shared_match_signature(match_data)
            occurrence_counts[base_key] += 1
            occurrence = occurrence_counts[base_key]
            match_data["match_key"] = hashlib.sha1(
                f"{base_key}|{occurrence}".encode("utf-8")
            ).hexdigest()[:20]
        match_data["player_alias"] = player_alias
        match_data["in_period"] = True
        matches.append(match_data)

    return matches


def parse_dakgg_api_matches(
    matches: list[dict[str, Any]],
    steam_id: str,
    player_alias: str,
    time_start: datetime,
    time_end: datetime,
    keep_modes: tuple[str, ...] | list[str] = ("Squad",),
) -> list[dict[str, Any]]:
    """将 DAK.GG API 原始比赛数据转换为内部结构并按目标时段过滤。"""
    parsed_matches = []
    for match in matches:
        parsed = api_match_to_record(match, steam_id, player_alias)
        if parsed is None:
            continue
        if not time_start <= parsed["approx_time"] <= time_end:
            continue
        if parsed["mode"] not in keep_modes or parsed["map"] == "Training Mode":
            continue
        parsed_matches.append(parsed)
    return parsed_matches


def api_match_to_record(
    match: dict[str, Any],
    steam_id: str,
    player_alias: str,
) -> dict[str, Any] | None:
    """将一条 API 比赛转换为稳定、可持久化的玩家比赛记录。"""
    participant = _find_api_participant(match, steam_id)
    match_id = match.get("id")
    if participant is None or not match_id:
        return None
    map_name = API_MAP_NAMES.get(
        str(match.get("mapName", "")),
        str(match.get("mapName") or "Unknown"),
    )
    created_at, precision = parse_time_label(
        str(match.get("createdAt", "")),
        datetime.now().astimezone(),
    )
    if created_at is None:
        return None
    traveled = sum(
        float(participant.get(field) or 0)
        for field in ("walkDistance", "rideDistance", "swimDistance")
    )
    time_survived = int(participant.get("timeSurvived") or 0)
    minutes, seconds = divmod(max(time_survived, 0), 60)
    return {
        "match_id": match_id,
        "match_key": f"dakgg:{match_id}",
        "mode": _api_mode_name(str(match.get("gameMode", ""))),
        "type": "Custom" if match.get("isCustomMatch") else "Normal",
        "placement": int(
            participant.get("teamRank") or participant.get("winPlace") or 0
        ),
        "total_teams": int(participant.get("teamTotal") or 0),
        "map": map_name,
        "weapon": _api_weapon_name(participant.get("mainWeapon")),
        "kills": int(participant.get("kills") or 0),
        "damage": round(float(participant.get("damageDealt") or 0)),
        "dbnos": int(participant.get("dbnos") or 0),
        "traveled": f"{traveled / 1000:.2f}km",
        "time_alive": f"{minutes}m {seconds}s",
        "longest_kill": f"{round(float(participant.get('longestKill') or 0))}m",
        "time_ago_text": match.get("createdAt"),
        "approx_time": created_at,
        "time_precision": precision,
        "teammates": [
            member["name"]
            for member in match.get("participants", [])
            if member.get("name")
        ],
        "player_alias": player_alias,
        "in_period": True,
    }


def csv_row_to_record(row: dict[str, str], player_alias: str) -> dict[str, Any]:
    """将 matches.csv 的一行恢复为内部比赛记录。"""
    created_at = datetime.fromisoformat(row["created_at"])
    return {
        "match_id": row["match_id"],
        "match_key": f"dakgg:{row['match_id']}",
        "mode": row["mode"],
        "type": row["type"],
        "placement": int(row["placement"]),
        "total_teams": int(row["total_teams"]),
        "map": row["map"],
        "weapon": row["weapon"] or None,
        "kills": int(row["kills"]),
        "damage": int(row["damage"]),
        "dbnos": int(row["dbnos"]),
        "traveled": row["traveled"],
        "time_alive": row["time_alive"],
        "longest_kill": row["longest_kill"],
        "time_ago_text": row["created_at"],
        "approx_time": created_at,
        "time_precision": "exact",
        "teammates": row["teammates"].split("|") if row["teammates"] else [],
        "player_alias": player_alias,
        "in_period": True,
    }


def _shared_match_signature(match: dict[str, Any]) -> str:
    shared = {
        "time": match.get("time_ago_text"),
        "mode": match.get("mode"),
        "type": match.get("type"),
        "placement": match.get("placement"),
        "total_teams": match.get("total_teams"),
        "map": match.get("map"),
        "teammates": sorted(set(match.get("teammates", []))),
    }
    return json.dumps(shared, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_one_match(section_text: str, scraped_at: datetime) -> dict[str, Any]:
    data: dict[str, Any] = {
        "match_id": None,
        "mode": None,
        "type": None,
        "placement": None,
        "total_teams": None,
        "map": None,
        "weapon": None,
        "kills": 0,
        "damage": 0,
        "dbnos": 0,
        "traveled": None,
        "time_alive": None,
        "longest_kill": None,
        "time_ago_text": None,
        "approx_time": None,
        "time_precision": None,
        "teammates": [],
        "in_period": False,
    }
    lines = [line.strip() for line in section_text.splitlines() if line.strip()]

    for index, line in enumerate(lines):
        if line.startswith("Match ID "):
            data["match_id"] = line.removeprefix("Match ID ").strip() or None
            continue

        mode_match = MODE_PATTERN.fullmatch(line)
        if mode_match:
            raw_mode = mode_match.group(1)
            mode_map = {"单排": "Solo", "双排": "Duo", "四排": "Squad"}
            data["mode"] = mode_map.get(raw_mode, raw_mode)
            data["type"] = mode_match.group(2) or "Unknown"
            continue

        placement_match = re.fullmatch(r"#(\d+)\s*/\s*(\d+)", line)
        if placement_match:
            data["placement"] = int(placement_match.group(1))
            data["total_teams"] = int(placement_match.group(2))
            continue

        parsed_time, precision = parse_time_label(line, scraped_at)
        if parsed_time is not None:
            data["time_ago_text"] = line
            data["approx_time"] = parsed_time
            data["time_precision"] = precision
            continue

        if line.startswith("Map"):
            value = _field_value(lines, index, line, "Map")
            if value in MAP_NAMES or value == "Training Mode":
                data["map"] = value
            elif value:
                data["map"] = value
            continue
        if line.startswith("Weapon"):
            value = _field_value(lines, index, line, "Weapon")
            if value and value != "-":
                data["weapon"] = value
            continue
        if line.startswith("Kills"):
            data["kills"] = _integer_field(lines, index, line, "Kills")
            continue
        if line.startswith("Damage"):
            data["damage"] = _integer_field(lines, index, line, "Damage")
            continue
        if line.startswith("DBNOs"):
            data["dbnos"] = _integer_field(lines, index, line, "DBNOs")
            continue
        if line.startswith("Traveled"):
            data["traveled"] = _field_value(lines, index, line, "Traveled")
            continue
        if line.startswith("Time Alive"):
            data["time_alive"] = _field_value(lines, index, line, "Time Alive")
            continue
        if line.startswith("Longest"):
            data["longest_kill"] = _field_value(lines, index, line, "Longest")
            continue

        teammate_match = re.fullmatch(r"-\s*\[([^\]]+)\]\([^)]+\)", line)
        if teammate_match:
            data["teammates"].append(teammate_match.group(1))

    return data


def _field_value(lines: list[str], index: int, line: str, label: str) -> str | None:
    value = line[len(label) :].strip()
    if not value and index + 1 < len(lines):
        value = lines[index + 1].strip()
    return value or None


def _integer_field(lines: list[str], index: int, line: str, label: str) -> int:
    value = _field_value(lines, index, line, label)
    try:
        return int((value or "0").replace(",", ""))
    except ValueError:
        return 0


def _find_api_participant(
    match: dict[str, Any],
    steam_id: str,
) -> dict[str, Any] | None:
    for participant in match.get("participants", []):
        if participant.get("name") == steam_id:
            return participant
    return None


def _api_mode_name(game_mode: str) -> str:
    normalized = game_mode.lower()
    if "squad" in normalized:
        return "Squad"
    if "duo" in normalized:
        return "Duo"
    if "solo" in normalized:
        return "Solo"
    return game_mode or "Unknown"


def _api_weapon_name(value: Any) -> str | None:
    if not value:
        return None
    code = str(value)
    if code in API_WEAPON_NAMES:
        return API_WEAPON_NAMES[code]
    return code.removeprefix("Weap").removesuffix("_C").replace("_", " ")
