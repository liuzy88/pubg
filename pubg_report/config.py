"""配置加载和报告时间范围计算。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PlayerConfig:
    alias: str
    steam_id: str


@dataclass(frozen=True)
class TimePeriodConfig:
    start_hour: int = 6
    start_minute: int = 0
    end_hour: int = 5
    end_minute: int = 59


@dataclass(frozen=True)
class DakggConfig:
    api_base_url: str
    page_count: int
    keep_modes: tuple[str, ...]


@dataclass(frozen=True)
class OutputConfig:
    data_dir: Path
    report_dir: Path


@dataclass(frozen=True)
class AppConfig:
    path: Path
    players: tuple[PlayerConfig, ...]
    time_period: TimePeriodConfig
    dakgg: DakggConfig
    output: OutputConfig


def _require(mapping: dict[str, Any], key: str, section: str) -> Any:
    if key not in mapping:
        raise ValueError(f"配置缺少 {section}.{key}")
    return mapping[key]


def load_config(path: str | Path) -> AppConfig:
    """加载并校验 conf.json，所有相对目录都相对于配置文件。"""
    config_path = Path(path).resolve()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    base_dir = config_path.parent

    players = tuple(
        PlayerConfig(
            alias=str(_require(player, "alias", "players[]")),
            steam_id=str(_require(player, "steam_id", "players[]")),
        )
        for player in _require(raw, "players", "root")
    )
    if not players:
        raise ValueError("players 至少需要配置一位玩家")
    if len({player.steam_id for player in players}) != len(players):
        raise ValueError("players 中存在重复 steam_id")

    time_raw = raw.get("time_period", {})
    time_period = TimePeriodConfig(
        start_hour=int(time_raw.get("start_hour", 6)),
        start_minute=int(time_raw.get("start_minute", 0)),
        end_hour=int(time_raw.get("end_hour", 5)),
        end_minute=int(time_raw.get("end_minute", 59)),
    )
    for label, value, maximum in (
        ("start_hour", time_period.start_hour, 23),
        ("end_hour", time_period.end_hour, 23),
        ("start_minute", time_period.start_minute, 59),
        ("end_minute", time_period.end_minute, 59),
    ):
        if not 0 <= value <= maximum:
            raise ValueError(f"time_period.{label} 超出范围")

    dakgg_raw = _require(raw, "dakgg", "root")
    page_count = int(dakgg_raw.get("page_count", 1))
    if page_count < 1:
        raise ValueError("dakgg.page_count 必须大于 0")
    dakgg = DakggConfig(
        api_base_url=str(_require(dakgg_raw, "api_base_url", "dakgg")).rstrip("/"),
        page_count=page_count,
        keep_modes=tuple(str(mode) for mode in dakgg_raw.get("keep_modes", ["Squad"])),
    )

    output_raw = raw.get("output", {})
    output = OutputConfig(
        data_dir=(base_dir / output_raw.get("data_dir", "data")).resolve(),
        report_dir=(base_dir / output_raw.get("report_dir", "reports")).resolve(),
    )
    return AppConfig(
        path=config_path,
        players=players,
        time_period=time_period,
        dakgg=dakgg,
        output=output,
    )


def get_time_range(
    days_ago: int = 1,
    period: TimePeriodConfig | None = None,
    reference_time: datetime | None = None,
) -> tuple[datetime, datetime, datetime]:
    """计算目标日报时段，默认是昨天 06:00 至今天 05:59:59.999999。"""
    if days_ago < 0:
        raise ValueError("days_ago 不能小于 0")
    period = period or TimePeriodConfig()
    now = reference_time or datetime.now().astimezone()
    start_day = now - timedelta(days=days_ago)
    period_start = start_day.replace(
        hour=period.start_hour,
        minute=period.start_minute,
        second=0,
        microsecond=0,
    )
    end_day = start_day + timedelta(days=1)
    period_end = end_day.replace(
        hour=period.end_hour,
        minute=period.end_minute,
        second=59,
        microsecond=999999,
    )
    return period_start, period_end, now
