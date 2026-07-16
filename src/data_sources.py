"""抓取清单及原始数据文件选择。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import AppConfig


MANIFEST_NAME = "fetch_manifest.json"


@dataclass(frozen=True)
class RawPage:
    page: int
    path: Path
    scraped_at: datetime
    format: str = "legacy-markdown"


@dataclass(frozen=True)
class RawSnapshot:
    scraped_at: datetime
    player_pages: dict[str, tuple[RawPage, ...]]
    source: str


def load_raw_snapshot(config: AppConfig) -> RawSnapshot:
    """只加载清单声明的本次抓取文件，避免历史分页残留混入。"""
    manifest_path = config.output.data_dir / MANIFEST_NAME
    if manifest_path.exists():
        return _snapshot_from_manifest(config, manifest_path)
    return _snapshot_from_configured_pages(config)


def _snapshot_from_manifest(config: AppConfig, manifest_path: Path) -> RawSnapshot:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    scraped_at = datetime.fromisoformat(raw["scraped_at"])
    players_raw = raw.get("players", {})
    player_pages: dict[str, tuple[RawPage, ...]] = {}
    matches_file = raw.get("matches_file")
    if matches_file:
        path = (config.output.data_dir / matches_file).resolve()
        if path.parent != config.output.data_dir:
            raise ValueError(f"抓取清单包含非法路径: {matches_file}")
        if not path.exists():
            raise FileNotFoundError(f"抓取清单声明的文件不存在: {path}")
        for player in config.players:
            player_pages[player.steam_id] = (
                RawPage(
                    page=0,
                    path=path,
                    scraped_at=scraped_at,
                    format=raw.get("format", "player-match-csv"),
                ),
            )
        return RawSnapshot(
            scraped_at=scraped_at,
            player_pages=player_pages,
            source=manifest_path.name,
        )

    for player in config.players:
        player_entry = players_raw.get(player.steam_id, {})
        if player_entry.get("file"):
            path = (config.output.data_dir / player_entry["file"]).resolve()
            if path.parent != config.output.data_dir:
                raise ValueError(f"抓取清单包含非法路径: {player_entry['file']}")
            if not path.exists():
                raise FileNotFoundError(f"抓取清单声明的文件不存在: {path}")
            player_pages[player.steam_id] = (
                RawPage(
                    page=0,
                    path=path,
                    scraped_at=datetime.fromisoformat(
                        player_entry.get("scraped_at", raw["scraped_at"])
                    ),
                    format=player_entry.get("format", "dakgg-api-json"),
                ),
            )
            continue

        page_entries = player_entry.get("pages", [])
        pages = []
        for entry in sorted(page_entries, key=lambda item: int(item["page"])):
            path = (config.output.data_dir / entry["file"]).resolve()
            if path.parent != config.output.data_dir:
                raise ValueError(f"抓取清单包含非法路径: {entry['file']}")
            if not path.exists():
                raise FileNotFoundError(f"抓取清单声明的文件不存在: {path}")
            page_scraped_at = datetime.fromisoformat(
                entry.get("scraped_at", raw["scraped_at"])
            )
            pages.append(
                RawPage(
                    page=int(entry["page"]),
                    path=path,
                    scraped_at=page_scraped_at,
                    format="legacy-markdown",
                )
            )
        player_pages[player.steam_id] = tuple(pages)

    return RawSnapshot(
        scraped_at=scraped_at,
        player_pages=player_pages,
        source=manifest_path.name,
    )


def _snapshot_from_configured_pages(config: AppConfig) -> RawSnapshot:
    """兼容旧数据：按安全页数上限选文件，并用文件时间固定解析基准。"""
    player_pages: dict[str, tuple[RawPage, ...]] = {}
    all_files: list[Path] = []
    for player in config.players:
        pages = []
        for page in range(1, config.dakgg.max_pages + 1):
            suffix = "" if page == 1 else f"_{page}"
            path = config.output.data_dir / f"{player.steam_id}_raw{suffix}.txt"
            if path.exists():
                pages.append(
                    RawPage(
                        page=page,
                        path=path,
                        scraped_at=datetime.fromtimestamp(
                            path.stat().st_mtime
                        ).astimezone(),
                        format="legacy-markdown",
                    )
                )
                all_files.append(path)
        player_pages[player.steam_id] = tuple(pages)

    if not all_files:
        raise FileNotFoundError(
            f"{config.output.data_dir} 中没有原始数据，也没有 {MANIFEST_NAME}"
        )
    latest_mtime = max(path.stat().st_mtime for path in all_files)
    scraped_at = datetime.fromtimestamp(latest_mtime).astimezone()
    return RawSnapshot(
        scraped_at=scraped_at,
        player_pages=player_pages,
        source="legacy-file-mtime",
    )


def build_manifest(
    scraped_at: datetime,
    player_entries: dict[str, dict[str, Any]],
    max_pages: int,
    target_start: datetime,
    target_end: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "scraped_at": scraped_at.isoformat(),
        "max_pages": max_pages,
        "target_time_start": target_start.isoformat(),
        "target_time_end": target_end.isoformat(),
        "players": dict(sorted(player_entries.items())),
    }
