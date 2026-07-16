#!/usr/bin/env python3
"""通过 DAK.GG 页面使用的 JSON API 抓取 PUBG 比赛记录。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    requests = None
    HTTPAdapter = None
    Retry = None

from src.config import AppConfig, get_time_range, load_config
from src.data_sources import MANIFEST_NAME, build_manifest
from src.parser import api_match_to_record


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://dak.gg",
    "Referer": "https://dak.gg/",
}

@dataclass(frozen=True)
class FetchedPage:
    matches: list[dict[str, Any]]
    match_count: int
    oldest_at: datetime | None
    newest_at: datetime | None
    has_more: bool


def create_session() -> requests.Session:
    if requests is None or HTTPAdapter is None or Retry is None:
        raise RuntimeError("缺少 requests，请先安装 requirements.txt")
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch_player_account(
    session: requests.Session,
    config: AppConfig,
    steam_id: str,
) -> str:
    response = session.get(
        f"{config.dakgg.api_base_url}/players/steam/{steam_id}",
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    account_id = data.get("player", {}).get("accountId")
    if not account_id:
        raise ValueError(f"DAK.GG 未返回 {steam_id} 的 accountId")
    return str(account_id)


def fetch_player_page(
    session: requests.Session,
    config: AppConfig,
    account_id: str,
    page: int,
) -> FetchedPage:
    response = session.get(
        f"{config.dakgg.api_base_url}/players/steam/{account_id}/matches",
        params={"page": page},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    matches = data.get("matches")
    if not isinstance(matches, list):
        raise ValueError("DAK.GG 比赛接口响应格式异常")
    if not matches:
        return FetchedPage([], 0, None, None, False)
    match_times = [
        parse_api_time(match["createdAt"])
        for match in matches
        if match.get("createdAt")
    ]
    if not match_times:
        raise ValueError("DAK.GG 比赛接口未返回 createdAt")
    meta = data.get("meta", {})
    current_page = int(meta.get("page") or page)
    per_page = int(meta.get("perPage") or len(matches))
    total_count = int(meta.get("totalCount") or len(matches))
    return FetchedPage(
        matches=matches,
        match_count=len(matches),
        oldest_at=min(match_times),
        newest_at=max(match_times),
        has_more=current_page * per_page < total_count,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="PUBG 数据采集")
    parser.add_argument("--player", help="只采集指定 steam_id")
    parser.add_argument("--pages", type=int, help="覆盖配置中的最大安全页数")
    parser.add_argument("--days-ago", type=int, default=1, help="目标报告日期：1=昨天")
    parser.add_argument("--config", default="conf.json", help="配置文件路径")
    args = parser.parse_args()
    if requests is None:
        sys.exit("请先安装依赖: pip install -r requirements.txt")

    config = load_config(args.config)
    max_pages = args.pages or config.dakgg.max_pages
    if max_pages < 1:
        parser.error("--pages 必须大于 0")
    players = list(config.players)
    if args.player:
        players = [player for player in players if player.steam_id == args.player]
        if not players:
            parser.error(f"未找到玩家: {args.player}")

    config.output.data_dir.mkdir(parents=True, exist_ok=True)
    scraped_at = datetime.now().astimezone()
    target_start, target_end, _ = get_time_range(
        args.days_ago,
        config.time_period,
        scraped_at,
    )
    session = create_session()
    manifest_path = config.output.data_dir / MANIFEST_NAME
    player_entries = _existing_player_entries(manifest_path) if args.player else {}
    ok_count = 0
    fail_count = 0
    print(
        f"📡 开始采集 {len(players)} 位玩家，目标时段 "
        f"{target_start.strftime('%Y-%m-%d %H:%M')} ~ "
        f"{target_end.strftime('%Y-%m-%d %H:%M')}，"
        f"每人最多 {max_pages} 页"
    )

    with tempfile.TemporaryDirectory(
        prefix=".fetch_",
        dir=config.output.data_dir,
    ) as staging_name:
        staging_dir = Path(staging_name)
        collected_rows: list[dict[str, str]] = []
        for player in players:
            collected_matches: list[dict[str, Any]] = []
            pages_fetched = 0
            oldest_match_at: datetime | None = None
            newest_match_at: datetime | None = None
            coverage_complete = False
            try:
                account_id = fetch_player_account(session, config, player.steam_id)
            except Exception as exc:
                print(f"❌ {player.alias:4s} 玩家信息 → {exc}")
                fail_count += 1
                continue

            for page in range(1, max_pages + 1):
                try:
                    fetched = fetch_player_page(
                        session,
                        config,
                        account_id,
                        page,
                    )
                    if not fetched.matches:
                        print(f"⏭️  {player.alias:4s} page{page} → 已到最后一页")
                        coverage_complete = True
                        break
                    collected_matches.extend(fetched.matches)
                    pages_fetched += 1
                    oldest_match_at = (
                        fetched.oldest_at
                        if oldest_match_at is None
                        else min(oldest_match_at, fetched.oldest_at)
                    )
                    newest_match_at = (
                        fetched.newest_at
                        if newest_match_at is None
                        else max(newest_match_at, fetched.newest_at)
                    )
                    ok_count += 1
                    print(
                        f"✅ {player.alias:4s} page{page} → "
                        f"{fetched.match_count} matches，最早 "
                        f"{fetched.oldest_at.astimezone().strftime('%m-%d %H:%M')}"
                    )
                    if page_covers_target_start(fetched, target_start):
                        print(f"🎯 {player.alias:4s} 已覆盖目标时段，停止翻页")
                        coverage_complete = True
                        break
                    if not fetched.has_more:
                        print(f"⏭️  {player.alias:4s} 已到最后一页")
                        coverage_complete = True
                        break
                except Exception as exc:
                    print(f"❌ {player.alias:4s} page{page} → {exc}")
                    fail_count += 1
                    break
                time.sleep(0.4)
            if not coverage_complete and collected_matches:
                print(
                    f"❌ {player.alias:4s} 达到 {max_pages} 页仍未覆盖目标时段；"
                    "请提高 dakgg.max_pages 或 --pages"
                )
                fail_count += 1
                continue

            for match in collected_matches:
                record = api_match_to_record(match, player.steam_id, player.alias)
                if record is not None:
                    collected_rows.append(_record_to_csv_row(record, player.steam_id))
            player_entries[player.steam_id] = {
                "pages_fetched": pages_fetched,
                "records_collected": len(collected_matches),
                "newest_match_at": (
                    newest_match_at.isoformat() if newest_match_at else None
                ),
                "oldest_match_at": (
                    oldest_match_at.isoformat() if oldest_match_at else None
                ),
            }

        if fail_count:
            print(f"采集失败: ✅ {ok_count} 页  ❌ {fail_count} 项；保留上一版数据")
            raise SystemExit(1)

        csv_path = config.output.data_dir / "matches.csv"
        new_count = _append_new_rows(csv_path, collected_rows)
        for player in players:
            for old_path in config.output.data_dir.glob(
                f"{player.steam_id}_raw*.txt"
            ):
                old_path.unlink()
            (config.output.data_dir / f"{player.steam_id}_matches.json").unlink(
                missing_ok=True
            )
        manifest = build_manifest(
            scraped_at,
            player_entries,
            max_pages,
            target_start,
            target_end,
        )
        manifest.update(
            {
                "matches_file": csv_path.name,
                "format": "player-match-csv",
                "new_rows": new_count,
            }
        )
        staged_manifest = staging_dir / manifest_path.name
        staged_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        staged_manifest.replace(manifest_path)

    print(f"🧾 抓取清单: {manifest_path}")
    print(f"采集完成: ✅ {ok_count} 页，新增 {new_count} 行  ❌ {fail_count} 项")


def parse_api_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"DAK.GG 时间缺少时区: {value}")
    return parsed


def page_covers_target_start(page: FetchedPage, target_start: datetime) -> bool:
    return page.oldest_at is not None and page.oldest_at <= target_start


def _existing_player_entries(
    manifest_path: Path,
) -> dict[str, dict[str, Any]]:
    if not manifest_path.exists():
        return {}
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return dict(raw.get("players", {}))


CSV_FIELDS = [
    "created_at",
    "match_id",
    "steam_id",
    "mode",
    "type",
    "placement",
    "total_teams",
    "map",
    "weapon",
    "kills",
    "damage",
    "dbnos",
    "traveled",
    "time_alive",
    "longest_kill",
    "teammates",
]


def _record_to_csv_row(record: dict[str, Any], steam_id: str) -> dict[str, str]:
    return {
        "created_at": record["approx_time"].isoformat(),
        "match_id": str(record["match_id"]),
        "steam_id": steam_id,
        "mode": str(record["mode"]),
        "type": str(record["type"]),
        "placement": str(record["placement"]),
        "total_teams": str(record["total_teams"]),
        "map": str(record["map"]),
        "weapon": str(record["weapon"] or ""),
        "kills": str(record["kills"]),
        "damage": str(record["damage"]),
        "dbnos": str(record["dbnos"]),
        "traveled": str(record["traveled"] or ""),
        "time_alive": str(record["time_alive"] or ""),
        "longest_kill": str(record["longest_kill"] or ""),
        "teammates": "|".join(record["teammates"]),
    }


def _append_new_rows(
    existing_path: Path,
    collected_rows: list[dict[str, str]],
) -> int:
    existing_keys: set[tuple[str, str]] = set()
    if existing_path.exists():
        with existing_path.open("r", encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != CSV_FIELDS:
                raise ValueError(f"{existing_path} CSV 列格式不兼容")
            for row in reader:
                existing_keys.add((row["match_id"], row["steam_id"]))

    new_rows = []
    for row in sorted(collected_rows, key=lambda item: item["created_at"]):
        key = (row["match_id"], row["steam_id"])
        if key not in existing_keys:
            existing_keys.add(key)
            new_rows.append(row)

    if not new_rows and existing_path.exists():
        return 0
    file_exists = existing_path.exists()
    with existing_path.open("a", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_rows)
    return len(new_rows)


if __name__ == "__main__":
    main()
