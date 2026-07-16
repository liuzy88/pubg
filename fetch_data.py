#!/usr/bin/env python3
"""通过 DAK.GG 页面使用的 JSON API 抓取 PUBG 比赛数据。"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
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

from pubg_report.config import AppConfig, load_config
from pubg_report.data_sources import MANIFEST_NAME, build_manifest


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

MAP_NAMES = {
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

WEAPON_NAMES = {
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
    steam_id: str,
    account_id: str,
    page: int,
) -> str:
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
        return ""
    return matches_json_to_markdown(matches, steam_id, account_id)


def matches_json_to_markdown(
    matches: list[dict[str, Any]],
    steam_id: str,
    account_id: str,
) -> str:
    sections = []
    for match in matches:
        participant = _find_participant(match, steam_id, account_id)
        if participant is None:
            continue
        mode = _mode_name(str(match.get("gameMode", "")))
        match_type = "Custom" if match.get("isCustomMatch") else "Normal"
        map_name = MAP_NAMES.get(
            str(match.get("mapName", "")),
            str(match.get("mapName") or "Unknown"),
        )
        weapon = _weapon_name(participant.get("mainWeapon"))
        traveled = sum(
            float(participant.get(field) or 0)
            for field in ("walkDistance", "rideDistance", "swimDistance")
        )
        teammates = "\n".join(
            f"- [{member.get('name', '')}]"
            f"(https://dak.gg/pubg/profile/steam/{member.get('name', '')})"
            for member in match.get("participants", [])
            if member.get("name")
        )
        section = f"""#### Match
Match ID {match.get("id", "")}
**{mode} _({match_type})_**
#{int(participant.get("teamRank") or participant.get("winPlace") or 0)}/{int(participant.get("teamTotal") or 0)}
{match.get("createdAt", "")}
Map {map_name}
Weapon {weapon or "-"}
Kills {int(participant.get("kills") or 0)}
Damage {round(float(participant.get("damageDealt") or 0))}
DBNOs {int(participant.get("dbnos") or 0)}
Traveled {traveled / 1000:.2f}km
Time Alive {_duration_text(int(participant.get("timeSurvived") or 0))}
Longest {round(float(participant.get("longestKill") or 0))}m
{teammates}
"""
        sections.append(section.strip())
    return "\n\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser(description="PUBG 数据采集")
    parser.add_argument("--player", help="只采集指定 steam_id")
    parser.add_argument("--pages", type=int, help="覆盖配置中的采集页数")
    parser.add_argument("--config", default="conf.json", help="配置文件路径")
    args = parser.parse_args()
    if requests is None:
        sys.exit("请先安装依赖: pip install -r requirements.txt")

    config = load_config(args.config)
    page_count = args.pages or config.dakgg.page_count
    if page_count < 1:
        parser.error("--pages 必须大于 0")
    players = list(config.players)
    if args.player:
        players = [player for player in players if player.steam_id == args.player]
        if not players:
            parser.error(f"未找到玩家: {args.player}")

    config.output.data_dir.mkdir(parents=True, exist_ok=True)
    scraped_at = datetime.now().astimezone()
    session = create_session()
    manifest_path = config.output.data_dir / MANIFEST_NAME
    player_pages = _existing_player_pages(manifest_path) if args.player else {}
    ok_count = 0
    fail_count = 0
    print(f"📡 开始采集 {len(players)} 位玩家 × 最多 {page_count} 页数据")

    with tempfile.TemporaryDirectory(
        prefix=".fetch_",
        dir=config.output.data_dir,
    ) as staging_name:
        staging_dir = Path(staging_name)
        staged_files: dict[str, list[Path]] = {}
        for player in players:
            pages: list[dict[str, object]] = []
            staged_files[player.steam_id] = []
            try:
                account_id = fetch_player_account(session, config, player.steam_id)
            except Exception as exc:
                print(f"❌ {player.alias:4s} 玩家信息 → {exc}")
                fail_count += 1
                continue

            for page in range(1, page_count + 1):
                final_path = _raw_path(config, player.steam_id, page)
                staged_path = staging_dir / final_path.name
                try:
                    text = fetch_player_page(
                        session,
                        config,
                        player.steam_id,
                        account_id,
                        page,
                    )
                    if not text:
                        print(f"⏭️  {player.alias:4s} page{page} → 已到最后一页")
                        break
                    page_scraped_at = datetime.now().astimezone()
                    staged_path.write_text(text, encoding="utf-8")
                    match_count = text.count("#### Match")
                    pages.append(
                        {
                            "page": page,
                            "file": final_path.name,
                            "match_count": match_count,
                            "scraped_at": page_scraped_at.isoformat(),
                        }
                    )
                    staged_files[player.steam_id].append(staged_path)
                    ok_count += 1
                    print(
                        f"✅ {player.alias:4s} page{page} → "
                        f"{match_count} matches  {final_path.name}"
                    )
                except Exception as exc:
                    print(f"❌ {player.alias:4s} page{page} → {exc}")
                    fail_count += 1
                    break
                time.sleep(0.4)
            player_pages[player.steam_id] = pages

        if fail_count:
            print(f"采集失败: ✅ {ok_count} 页  ❌ {fail_count} 项；保留上一版数据")
            raise SystemExit(1)

        for player in players:
            for old_path in config.output.data_dir.glob(
                f"{player.steam_id}_raw*.txt"
            ):
                old_path.unlink()
            for staged_path in staged_files[player.steam_id]:
                staged_path.replace(config.output.data_dir / staged_path.name)

        manifest_path.write_text(
            json.dumps(
                build_manifest(scraped_at, player_pages, page_count),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    print(f"🧾 抓取清单: {manifest_path}")
    print(f"采集完成: ✅ {ok_count} 页  ❌ {fail_count} 项")


def _find_participant(
    match: dict[str, Any],
    steam_id: str,
    account_id: str,
) -> dict[str, Any] | None:
    for participant in match.get("participants", []):
        if (
            participant.get("playerId") == account_id
            or participant.get("name") == steam_id
        ):
            return participant
    return None


def _mode_name(game_mode: str) -> str:
    normalized = game_mode.lower()
    if "squad" in normalized:
        return "Squad"
    if "duo" in normalized:
        return "Duo"
    if "solo" in normalized:
        return "Solo"
    return game_mode or "Unknown"


def _weapon_name(value: Any) -> str | None:
    if not value:
        return None
    code = str(value)
    if code in WEAPON_NAMES:
        return WEAPON_NAMES[code]
    return code.removeprefix("Weap").removesuffix("_C").replace("_", " ")


def _duration_text(seconds: int) -> str:
    minutes, remaining = divmod(max(seconds, 0), 60)
    return f"{minutes}m {remaining}s"


def _raw_path(config: AppConfig, steam_id: str, page: int) -> Path:
    suffix = "" if page == 1 else f"_{page}"
    return config.output.data_dir / f"{steam_id}_raw{suffix}.txt"


def _existing_player_pages(
    manifest_path: Path,
) -> dict[str, list[dict[str, object]]]:
    if not manifest_path.exists():
        return {}
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        steam_id: list(player_data.get("pages", []))
        for steam_id, player_data in raw.get("players", {}).items()
    }


if __name__ == "__main__":
    main()
