"""可复现的称号与评语生成。"""

from __future__ import annotations

import random
from typing import Any


def generate_titles_and_comments(
    stats: dict[str, dict[str, Any]],
    team_stats: dict[str, Any],
    rng: random.Random | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    rng = rng or random.Random(0)
    players = list(stats.values())
    if not players:
        return [], []

    titles: list[dict[str, str]] = []
    comments: list[str] = []
    active = [player for player in players if player["match_count"] > 0]
    clown = lambda: rng.choice(["🤡", "😅", "💩", "🤦", "😬"])

    if active:
        kill_king = max(active, key=lambda player: player["total_kills"])
        titles.append(
            {
                "title": "🔫 击杀王",
                "player": kill_king["alias"],
                "value": f"{kill_king['total_kills']} 杀",
                "comment": (
                    f"枪管子都打冒烟了！{kill_king['alias']}的瞄准镜里全是人头。"
                    if kill_king["total_kills"] > 5
                    else f"勉强拿了个击杀王，但{clown()}这数据也好意思？"
                ),
            }
        )

        damage_king = max(active, key=lambda player: player["total_damage"])
        titles.append(
            {
                "title": "💥 伤害王",
                "player": damage_king["alias"],
                "value": f"{damage_king['total_damage']:,} 伤害",
                "comment": (
                    f"每颗子弹都写着{rng.choice(['尊重', '恐惧', '卧槽'])}！"
                    if damage_king["total_damage"] > 500
                    else "这伤害量...打得挺热闹的，就是没打死人。"
                ),
            }
        )

        kd_king = max(active, key=lambda player: player["estimated_kd"])
        titles.append(
            {
                "title": "📈 估算KD之王",
                "player": kd_king["alias"],
                "value": f"估算KD {kd_king['estimated_kd']}",
                "comment": (
                    f"数据不会说谎——{kd_king['alias']}的估算KD说明了一切。"
                    if kd_king["estimated_kd"] >= 2
                    else f"估算KD {kd_king['estimated_kd']}...{clown()} 在玩跳伞模拟器？"
                ),
            }
        )

        chicken_king = max(active, key=lambda player: player["chicken_dinners"])
        if chicken_king["chicken_dinners"] > 0:
            titles.append(
                {
                    "title": "🍗 吃鸡王者",
                    "player": chicken_king["alias"],
                    "value": f"{chicken_king['chicken_dinners']} 次吃鸡",
                    "comment": (
                        "Winner Winner Chicken Dinner! 🐔 鸡都吃撑了！"
                        if chicken_king["chicken_dinners"] >= 2
                        else "就吃了一次鸡，但也是鸡！比鸡屁股都没摸到的强。"
                    ),
                }
            )

        avg_damage_king = max(active, key=lambda player: player["avg_damage"])
        titles.append(
            {
                "title": "🎯 场均之王",
                "player": avg_damage_king["alias"],
                "value": f"场均 {avg_damage_king['avg_damage']} 伤害",
                "comment": (
                    "稳如老狗，每把都有稳定输出。"
                    if avg_damage_king["avg_damage"] > 150
                    else f"场均{avg_damage_king['avg_damage']}...打绷带都不止这么多。"
                ),
            }
        )

        if len(active) >= 2:
            kill_min = min(active, key=lambda player: player["total_kills"])
            if kill_min["total_kills"] == 0 and kill_min["match_count"] > 1:
                titles.append(
                    {
                        "title": "🕊️ 和平大使",
                        "player": kill_min["alias"],
                        "value": "0 击杀",
                        "comment": f"真正的和平主义者！{kill_min['alias']}：'我是来交朋友的'",
                    }
                )
            kd_min = min(active, key=lambda player: player["estimated_kd"])
            if kd_min["estimated_kd"] < 0.5:
                titles.append(
                    {
                        "title": "💀 快递员",
                        "player": kd_min["alias"],
                        "value": f"估算KD {kd_min['estimated_kd']}",
                        "comment": f"{kd_min['alias']}：'落地→搜装备→送快递→下一把'，物流行业标杆！",
                    }
                )

    combos = team_stats.get("combos", [])
    if combos:
        top = combos[0]
        names = [player["alias"] for player in top["players"]]
        titles.append(
            {
                "title": "🤝 最佳搭档",
                "player": " & ".join(names),
                "value": f"{top['games']} 场同队",
                "comment": (
                    f"形影不离！{'和'.join(names)}简直是用502粘在一起了。"
                    if top["games"] >= 3
                    else "也就一起打了几把，别想太多。"
                ),
            }
        )

    comment_templates = [
        ("{name}今天枪法如神，建议去参加职业联赛（认真脸）", lambda p: p["estimated_kd"] >= 3),
        ("{name}手感火热！保持了高水准发挥", lambda p: p["estimated_kd"] >= 2),
        ("{name}很稳，队友的坚实后盾 👍", lambda p: p["avg_damage"] >= 200),
        ("{name}吃鸡了！今晚可以吹一年 🍗", lambda p: p["chicken_dinners"] >= 2),
        ("{name}表现...建议去训练场多待会儿 😅", lambda p: p["estimated_kd"] < 0.5),
        ("{name}：我不是在送，我是在做慈善 🙏", lambda p: p["total_kills"] == 0 and p["match_count"] >= 2),
        ("{name}落地成盒专业户，跳伞姿势倒是挺帅的 ✈️", lambda p: p["avg_damage"] < 50),
        ("{name}中规中矩，不是最菜的也不是最强的", lambda p: True),
    ]
    for player in players:
        if player["match_count"] == 0:
            comments.append(f"⛔ {player['alias']} 昨天摸鱼了，一场没打！装死也不是这么装的！")
            continue
        for template, condition in comment_templates:
            if condition(player):
                comments.append(template.format(name=player["alias"]))
                break

    return titles, comments
