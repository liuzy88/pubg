"""HTML 报告渲染，模板和样式与业务计算分离。"""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from string import Template
from typing import Any


PACKAGE_DIR = Path(__file__).parent
TEMPLATE_PATH = PACKAGE_DIR / "templates" / "report.html"
CSS_PATH = PACKAGE_DIR / "static" / "report.css"
MAP_ZH = {
    "Erangel": "艾伦格",
    "Miramar": "米拉玛",
    "Sanhok": "萨诺",
    "Vikendi": "维寒迪",
    "Karakin": "卡拉金",
    "Paramo": "帕拉莫",
    "Haven": "褐湾",
    "Taego": "泰戈",
    "Deston": "帝斯顿",
    "Rondo": "荣都",
    "Tiger": "老虎",
}


def generate_html_report(
    stats: dict[str, dict[str, Any]],
    team_stats: dict[str, Any],
    titles: list[dict[str, str]],
    comments: list[str],
    time_start: datetime,
    time_end: datetime,
    generated_at: datetime,
) -> str:
    sorted_players = sorted(
        stats.values(),
        key=lambda player: (
            player["match_count"] > 0,
            player["total_kills"],
            player["total_damage"],
        ),
        reverse=True,
    )
    active_players = [player for player in sorted_players if player["match_count"] > 0]
    podium = active_players[:3]
    podium_order = [
        podium[1] if len(podium) > 1 else None,
        podium[0] if podium else None,
        podium[2] if len(podium) > 2 else None,
    ]
    podium_labels = ["🥈", "👑", "🥉"]
    podium_html = "".join(
        _player_card(player, podium_labels[index])
        if player
        else '<div class="podium-placeholder" aria-hidden="true"></div>'
        for index, player in enumerate(podium_order)
    )

    podium_ids = {player["steam_id"] for player in podium}
    rest = [
        player for player in sorted_players if player["steam_id"] not in podium_ids
    ]
    labels = ["4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
    rows = "".join(
        _player_row(player, labels[index] if index < len(labels) else "")
        for index, player in enumerate(rest)
    )
    rest_section = (
        '<h2 class="section-title">👥 其他选手</h2>'
        '<div class="player-table-wrap"><table class="player-table">'
        "<thead><tr><th>选手</th><th>击杀</th><th>伤害</th>"
        "<th>估算KD</th><th>场均 杀/伤</th><th>吃鸡</th><th>最佳</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
        if rows
        else ""
    )

    titles_html = "".join(
        '<span class="tl-badge">'
        f"<b>{_e(title['title'])}</b> {_e(title['player'])} · {_e(title['value'])}"
        f"<small>——{_e(title['comment'])}</small></span>"
        for title in titles
    )
    comments_html = "".join(f"<li>{_e(comment)}</li>" for comment in comments)
    combos = team_stats.get("combos", [])[:3]
    combos_html = (
        " · ".join(
            "<b>"
            + " + ".join(_e(player["alias"]) for player in combo["players"])
            + f"</b> {combo['games']}场🍗x{combo['chickens']}"
            for combo in combos
        )
        if combos
        else "昨天各玩各的 🥲"
    )

    player_games = sum(player["match_count"] for player in stats.values())
    total_kills = sum(player["total_kills"] for player in stats.values())
    total_damage = sum(player["total_damage"] for player in stats.values())
    active_count = len(active_players)
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    template = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
    return template.substitute(
        css=CSS_PATH.read_text(encoding="utf-8"),
        date_str=time_start.strftime("%Y年%m月%d日"),
        friendly_date=(
            f"📅 {time_start.year}年{time_start.month:02d}月{time_start.day:02d}日 "
            f"{weekdays[time_start.weekday()]}"
        ),
        time_range=(
            f"{time_start.strftime('%H:%M')} — 次日 {time_end.strftime('%H:%M')}"
        ),
        active_count=active_count,
        player_count=len(stats),
        unique_matches=team_stats.get("unique_match_count", player_games),
        player_games=player_games,
        total_kills=total_kills,
        total_damage=f"{total_damage:,}",
        unique_chickens=team_stats.get("unique_chicken_count", 0),
        avg_damage=f"{round(total_damage / max(active_count, 1)):,}",
        podium_html=podium_html,
        rest_section=rest_section,
        titles_html=titles_html,
        comments_html=comments_html,
        combos_html=combos_html,
        generated_at=generated_at.strftime("%Y-%m-%d %H:%M"),
    )


def _card_class(player: dict[str, Any]) -> str:
    if player["match_count"] == 0:
        return "card-absent"
    estimated_kd = player["estimated_kd"]
    if estimated_kd >= 2.5:
        return "card-god"
    if estimated_kd >= 1.5:
        return "card-good"
    if estimated_kd >= 0.8:
        return "card-avg"
    return "card-bad"


def _player_card(player: dict[str, Any], rank_label: str) -> str:
    best = f"#{player['best_placement']}" if player["best_placement"] != 999 else "-"
    estimated_kd = player["estimated_kd"]
    kd_class = "clr-gold" if estimated_kd >= 2 else ("clr-red" if estimated_kd < 0.8 else "")
    maps_html = "".join(
        f"<i>{_e(MAP_ZH.get(map_name, map_name))}</i>"
        for map_name, _count in sorted(
            player.get("map_stats", {}).items(),
            key=lambda item: -item[1],
        )[:3]
    )
    return (
        f'<article class="pcard {_card_class(player)}"><div class="pc-head">'
        '<div class="pc-player">'
        f'<div class="pc-rank" aria-hidden="true">{_e(rank_label)}</div>'
        '<div class="pc-identity">'
        f'<div class="pc-name">{_e(player["alias"])}</div>'
        f'<div class="pc-sub">{player["match_count"]} 场作战</div></div></div>'
        f'<div class="pc-kills"><strong>{player["total_kills"]}</strong><span>击杀</span></div>'
        '</div><div class="pc-metrics">'
        f'<div><span>总伤害</span><b>{player["total_damage"]:,}</b></div>'
        f'<div><span>估算KD</span><b class="{kd_class}">{estimated_kd}</b></div>'
        f'<div><span>吃鸡</span><b>🍗 × {player["chicken_dinners"]}</b></div>'
        f'<div><span>场均击杀</span><b>{player["avg_kills"]}</b></div>'
        f'<div><span>场均伤害</span><b>{player["avg_damage"]:.0f}</b></div>'
        f'<div><span>最佳排名</span><b>{best}</b></div></div>'
        + (f'<div class="pc-tags">{maps_html}</div>' if maps_html else "")
        + "</article>"
    )


def _player_row(player: dict[str, Any], rank_label: str) -> str:
    best = f"#{player['best_placement']}" if player["best_placement"] != 999 else "-"
    estimated_kd = player["estimated_kd"]
    kd_class = "clr-gold" if estimated_kd >= 2 else ("clr-red" if estimated_kd < 0.8 else "")
    return (
        f'<tr class="{_card_class(player)}"><th scope="row">'
        f'<span class="pt-rank">{_e(rank_label)}</span><strong>{_e(player["alias"])}</strong>'
        f'<small>{player["match_count"]}场</small></th>'
        f'<td class="pt-kills">{player["total_kills"]}</td>'
        f'<td>{player["total_damage"]:,}</td><td class="{kd_class}">{estimated_kd}</td>'
        f'<td>{player["avg_kills"]}/{player["avg_damage"]:.0f}</td>'
        f'<td>🍗{player["chicken_dinners"]}</td><td>{best}</td></tr>'
    )


def _e(value: Any) -> str:
    return escape(str(value), quote=True)
