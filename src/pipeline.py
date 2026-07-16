"""日报生成主流程。"""

from __future__ import annotations

import csv
import json
import random
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .awards import generate_titles_and_comments
from .config import AppConfig, get_time_range, load_config
from .data_sources import load_raw_snapshot
from .parser import csv_row_to_record, parse_dakgg_api_matches, parse_dakgg_markdown
from .renderer import generate_html_report
from .screenshot import generate_report_screenshot
from .stats import compute_stats, compute_team_stats


def run(
    days_ago: int = 1,
    config_path: str | Path | None = None,
    generate_screenshot: bool = True,
    reference_time: datetime | None = None,
) -> str:
    project_dir = Path(__file__).resolve().parent.parent
    config = load_config(config_path or project_dir / "conf.json")
    print("=" * 60)
    print("🎮 PUBG 每日战报生成器 v3.0")
    print("=" * 60)

    time_start, time_end, generated_at = get_time_range(
        days_ago,
        config.time_period,
        reference_time,
    )
    print(f"✅ 加载 {len(config.players)} 位玩家配置")
    print(
        f"📅 数据时段: {time_start.strftime('%Y-%m-%d %H:%M')} ~ "
        f"{time_end.strftime('%Y-%m-%d %H:%M')}"
    )

    config.output.data_dir.mkdir(parents=True, exist_ok=True)
    config.output.report_dir.mkdir(parents=True, exist_ok=True)
    snapshot = load_raw_snapshot(config)
    print(f"🕒 抓取时间: {snapshot.scraped_at.isoformat()}")
    if snapshot.source == "legacy-file-mtime":
        print("⚠️  未找到抓取清单，暂用原始文件时间；下次 fetch_matches.py 会自动生成清单")

    date_str = time_start.strftime("%Y%m%d")
    all_player_data = _parse_players(
        config,
        snapshot,
        time_start,
        time_end,
        persist_latest_parsed=days_ago == 1,
    )
    stats, all_matches = compute_stats(all_player_data)
    team_stats = compute_team_stats(all_matches, all_player_data)
    titles, comments = generate_titles_and_comments(
        stats,
        team_stats,
        rng=random.Random(int(date_str)),
    )
    html = generate_html_report(
        stats,
        team_stats,
        titles,
        comments,
        time_start,
        time_end,
        generated_at,
    )

    report_path = config.output.report_dir / f"pubg_report_{date_str}.html"
    report_path.write_text(html, encoding="utf-8")
    screenshot_path = report_path.with_suffix(".png")
    screenshot_ok = False
    if generate_screenshot:
        try:
            generate_report_screenshot(report_path, screenshot_path)
            screenshot_ok = True
            print(f"📸 战报截图已生成: {screenshot_path}")
        except Exception as exc:
            print(f"⚠️  战报截图生成失败: {exc}")

    if days_ago == 1:
        (config.output.report_dir / "latest.html").write_text(html, encoding="utf-8")
        if screenshot_ok:
            shutil.copyfile(
                screenshot_path,
                config.output.report_dir / "latest.png",
            )
        print("📌 已同步 latest.html" + (" / latest.png" if screenshot_ok else ""))

    stats_path = config.output.data_dir / f"stats_{date_str}.json"
    stats_path.write_text(
        json.dumps(
            {
                "date": date_str,
                "time_start": time_start.isoformat(),
                "time_end": time_end.isoformat(),
                "generated_at": generated_at.isoformat(),
                "scraped_at": snapshot.scraped_at.isoformat(),
                "raw_snapshot_source": snapshot.source,
                "stats": {
                    steam_id: {
                        key: value
                        for key, value in player_stats.items()
                        if key not in {"map_stats", "weapon_stats", "kda"}
                    }
                    for steam_id, player_stats in stats.items()
                },
                "team_stats": team_stats,
                "titles": titles,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"✅ 战报生成完成: {report_path} "
        f"({team_stats['unique_match_count']} 场实际比赛 / {len(all_matches)} 条玩家记录)"
    )
    return str(report_path)


def _parse_players(
    config: AppConfig,
    snapshot: Any,
    time_start: datetime,
    time_end: datetime,
    persist_latest_parsed: bool,
) -> dict[str, dict[str, Any]]:
    all_player_data: dict[str, dict[str, Any]] = {}
    for player in config.players:
        raw_pages = snapshot.player_pages.get(player.steam_id, ())
        if not raw_pages:
            print(f"⚠️  {player.alias}: 本次抓取清单中没有数据文件")
            all_player_data[player.steam_id] = {
                "alias": player.alias,
                "steam_id": player.steam_id,
                "matches": [],
            }
            continue

        matches = []
        occurrence_counts: dict[str, int] = defaultdict(int)
        for raw_page in raw_pages:
            if raw_page.format == "player-match-csv":
                with raw_page.path.open("r", encoding="utf-8", newline="") as source:
                    for row in csv.DictReader(source):
                        if row.get("steam_id") != player.steam_id:
                            continue
                        record = csv_row_to_record(row, player.alias)
                        if not time_start <= record["approx_time"] <= time_end:
                            continue
                        if record["mode"] not in config.dakgg.keep_modes:
                            continue
                        if record["map"] == "Training Mode":
                            continue
                        matches.append(record)
            elif raw_page.format == "dakgg-api-json":
                payload = json.loads(raw_page.path.read_text(encoding="utf-8"))
                api_matches = payload.get("matches")
                if not isinstance(api_matches, list):
                    raise ValueError(f"比赛数据文件格式异常: {raw_page.path}")
                matches.extend(
                    parse_dakgg_api_matches(
                        api_matches,
                        player.steam_id,
                        player.alias,
                        time_start,
                        time_end,
                        config.dakgg.keep_modes,
                    )
                )
            else:
                matches.extend(
                    parse_dakgg_markdown(
                        raw_page.path.read_text(encoding="utf-8"),
                        player.alias,
                        raw_page.scraped_at,
                        time_start,
                        time_end,
                        config.dakgg.keep_modes,
                        occurrence_counts,
                    )
                )
        all_player_data[player.steam_id] = {
            "alias": player.alias,
            "steam_id": player.steam_id,
            "matches": matches,
        }
        if persist_latest_parsed:
            parsed_path = config.output.data_dir / f"{player.steam_id}_parsed.json"
            parsed_path.write_text(
                json.dumps(
                    all_player_data[player.steam_id],
                    ensure_ascii=False,
                    indent=2,
                    default=_json_serial,
                ),
                encoding="utf-8",
            )
        print(f"✅ {player.alias}: 解析到 {len(matches)} 场时段内比赛")
    return all_player_data


def _json_serial(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Type {type(value)} not serializable")
