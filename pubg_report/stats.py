"""玩家和队伍统计。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def compute_stats(
    all_player_data: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    stats: dict[str, dict[str, Any]] = {}
    all_matches: list[dict[str, Any]] = []

    for steam_id, player_data in all_player_data.items():
        alias = player_data["alias"]
        matches = player_data.get("matches", [])
        if not matches:
            stats[steam_id] = _empty_stats(alias, steam_id)
            continue

        total_kills = sum(match.get("kills", 0) for match in matches)
        total_damage = sum(match.get("damage", 0) for match in matches)
        total_dbnos = sum(match.get("dbnos", 0) for match in matches)
        match_count = len(matches)
        chicken_dinners = sum(match.get("placement") == 1 for match in matches)
        top10 = sum(match.get("placement", 999) <= 10 for match in matches)
        estimated_deaths = sum(match.get("placement", 0) > 1 for match in matches)
        estimated_kd = round(total_kills / max(estimated_deaths, 1), 2)

        map_stats: dict[str, int] = defaultdict(int)
        weapon_stats: dict[str, int] = defaultdict(int)
        for match in matches:
            if match.get("map"):
                map_stats[match["map"]] += 1
            if match.get("weapon") not in {None, "-", "None", ""}:
                weapon_stats[match["weapon"]] += 1
            match["player_alias"] = alias
            match["player_steam_id"] = steam_id

        stats[steam_id] = {
            "alias": alias,
            "steam_id": steam_id,
            "match_count": match_count,
            "total_kills": total_kills,
            "total_damage": total_damage,
            "total_dbnos": total_dbnos,
            "estimated_kd": estimated_kd,
            "kda": estimated_kd,
            "avg_kills": round(total_kills / match_count, 2),
            "avg_damage": round(total_damage / match_count, 1),
            "chicken_dinners": chicken_dinners,
            "chicken_rate": round(chicken_dinners / match_count * 100, 1),
            "top10_rate": round(top10 / match_count * 100, 1),
            "best_placement": min(
                (match.get("placement", 999) for match in matches),
                default=999,
            ),
            "map_stats": dict(map_stats),
            "weapon_stats": dict(weapon_stats),
        }
        all_matches.extend(matches)

    return stats, all_matches


def _empty_stats(alias: str, steam_id: str) -> dict[str, Any]:
    return {
        "alias": alias,
        "steam_id": steam_id,
        "match_count": 0,
        "total_kills": 0,
        "total_damage": 0,
        "total_dbnos": 0,
        "estimated_kd": 0,
        "kda": 0,
        "avg_kills": 0,
        "avg_damage": 0,
        "chicken_dinners": 0,
        "chicken_rate": 0,
        "top10_rate": 0,
        "best_placement": 999,
        "map_stats": {},
        "weapon_stats": {},
    }


def compute_team_stats(
    all_matches: list[dict[str, Any]],
    all_player_data: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """先按 match_key 合并玩家视角，再统计真实比赛和搭档组合。"""
    player_aliases = {
        steam_id: data["alias"] for steam_id, data in all_player_data.items()
    }
    alias_to_id = {
        data["alias"]: steam_id for steam_id, data in all_player_data.items()
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, match in enumerate(all_matches):
        key = match.get("match_key") or f"unkeyed-{index}"
        grouped[key].append(match)

    combo_stats: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"games": 0, "chickens": 0, "placements": []}
    )
    unique_chickens = 0
    team_games = 0

    for perspectives in grouped.values():
        tracked_ids: set[str] = {
            match["player_steam_id"]
            for match in perspectives
            if match.get("player_steam_id") in player_aliases
        }
        for match in perspectives:
            for teammate in match.get("teammates", []):
                steam_id = alias_to_id.get(teammate)
                if steam_id:
                    tracked_ids.add(steam_id)

        placements = [
            match["placement"]
            for match in perspectives
            if isinstance(match.get("placement"), int)
        ]
        placement = min(placements, default=999)
        is_chicken = placement == 1
        if is_chicken:
            unique_chickens += 1
        if len(tracked_ids) >= 2:
            team_games += 1

        ids = sorted(tracked_ids)
        for left_index, left in enumerate(ids):
            for right in ids[left_index + 1 :]:
                pair = (left, right)
                combo_stats[pair]["games"] += 1
                combo_stats[pair]["placements"].append(placement)
                if is_chicken:
                    combo_stats[pair]["chickens"] += 1

    combos = []
    for pair, values in combo_stats.items():
        placements = values["placements"]
        combos.append(
            {
                "players": [
                    {"steam_id": steam_id, "alias": player_aliases[steam_id]}
                    for steam_id in pair
                ],
                "games": values["games"],
                "chickens": values["chickens"],
                "avg_placement": round(sum(placements) / len(placements), 1),
            }
        )
    combos.sort(key=lambda item: (-item["games"], item["avg_placement"]))

    return {
        "unique_match_count": len(grouped),
        "unique_chicken_count": unique_chickens,
        "team_games_count": team_games,
        "combos": combos,
    }
