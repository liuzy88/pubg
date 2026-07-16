#!/usr/bin/env python3
"""
PUBG 每日战报 - 数据处理与报告生成模块
从 WebFetch 获取的 dak.gg 页面文本中解析比赛数据，生成战报
"""

import json
import re
import random
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

SCRIPT_DIR = Path(__file__).parent
CONF_PATH = SCRIPT_DIR / "conf.json"
DATA_DIR = SCRIPT_DIR / "data"
REPORT_DIR = SCRIPT_DIR / "reports"

# ============================================================
# 时间处理
# ============================================================

def get_time_range(days_ago=1):
    """计算目标时间段：指定天数前的那天 06:00 - 次日 05:59
    days_ago=1: 昨天 06:00 ~ 今天 05:59
    days_ago=2: 前天 06:00 ~ 昨天 05:59
    """
    now = datetime.now()
    start_day = now - timedelta(days=days_ago)
    period_start = start_day.replace(hour=6, minute=0, second=0, microsecond=0)
    end_day = start_day + timedelta(days=1)
    period_end = end_day.replace(hour=5, minute=59, second=59, microsecond=999999)
    return period_start, period_end, now


def parse_time_ago(text, reference_time):
    """解析 'Xh ago', 'Xd ago', 'Xm ago' 等时间文本"""
    text = text.strip().lower()
    match = re.search(r'(\d+)\s*(h|d|m|min)\s*ago', text)
    if match:
        value, unit = int(match.group(1)), match.group(2)
        if unit in ('m', 'min'):
            return reference_time - timedelta(minutes=value)
        elif unit == 'h':
            return reference_time - timedelta(hours=value)
        elif unit == 'd':
            return reference_time - timedelta(days=value)
    return None


# ============================================================
# Markdown 文本解析（解析 WebFetch 返回的 dak.gg 页面内容）
# ============================================================

# 武器名称列表（英文和中文）
WEAPON_NAMES = {
    # 突击步枪
    "M416", "M16A4", "SCAR-L", "G36C", "QBZ", "K2", "AUG A3", "Beryl",
    "AKM", "Groza", "ACE32", "MK47", "FAMAS",
    # 冲锋枪
    "UMP45", "Vector", "Tommy Gun", "MP5K", "PP-19", "P90", "JS9", "MP9",
    "Micro UZI", "UZI", "Bizon",
    # 狙击步枪
    "M24", "Kar98k", "Mosin", "AWM", "Win94", "Lynx",
    # 精确射手步枪
    "SKS", "SLR", "Mini 14", "Mk14", "QBU", "VSS", "Dragunov", "Mk12",
    # 霰弹枪
    "S12K", "S1897", "DBS", "O12", "S686",
    # 轻机枪
    "DP-28", "M249", "MG3",
    # 手枪
    "P18C", "P92", "P1911", "R1895", "Skorpion", "Deagle", "R45", "Sawed-Off",
    # 其他
    "Crossbow", "Panzerfaust", "Mortar", "M79",
}

MAP_NAMES = {"Erangel", "Miramar", "Sanhok", "Vikendi", "Karakin", "Paramo", "Haven", "Taego", "Deston", "Rondo", "Tiger"}

MAP_ZH = {"Erangel": "艾伦格", "Miramar": "米拉玛", "Sanhok": "萨诺", "Vikendi": "维寒迪", "Karakin": "卡拉金", "Paramo": "帕拉莫", "Haven": "褐湾", "Taego": "泰戈", "Deston": "帝斯顿", "Rondo": "荣都", "Tiger": "虎山"}


def parse_dakgg_markdown(text, player_alias, scrape_time, time_start, time_end, config=None):
    """
    从 WebFetch 返回的 dak.gg 页面文本中提取比赛数据
    自动过滤训练场和 Solo/Duo 模式（根据 conf.json 配置）
    """
    matches = []
    
    # 按 "#### 매치 요약 정보" 或 "#### マッチ" 分割
    sections = re.split(r'####\s*(?:매치\s*요약\s*정보|マッチ|Match|比赛)', text)
    
    for section in sections[1:]:  # 跳过第一个空段
        match_data = _parse_one_match(section.strip(), scrape_time)
        if match_data and match_data.get("placement") is not None:
            # 过滤训练场（map == "Training Mode" — 一律排除）
            if match_data.get("map") == "Training Mode":
                continue
            
            # 只保留 Squad/四排 模式
            mode = match_data.get("mode", "")
            if config and "dakgg" in config:
                keep_modes = config["dakgg"].get("keep_modes", ["Squad", "四排"])
                if mode and mode not in keep_modes:
                    continue
            
            # 检查时间范围
            if match_data.get("approx_time"):
                match_data["in_period"] = time_start <= match_data["approx_time"] <= time_end
            else:
                match_data["in_period"] = True
            
            if match_data["in_period"]:
                match_data["player_alias"] = player_alias
                matches.append(match_data)
    
    return matches


def _parse_one_match(section_text, scrape_time):
    """解析单个比赛区块"""
    data = {
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
        "teammates": [],
        "in_period": False,
    }
    
    lines = [l.strip() for l in section_text.split('\n') if l.strip()]
    
    for i, line in enumerate(lines):
        # 跳过 "More" 按钮文本
        if line == "More":
            continue
        
        # 模式和类型: **Squad _(Normal)_** 或 **四排 _(Normal)_**
        mode_match = re.match(r'\*{0,2}(Solo|Duo|Squad|单排|双排|四排)\s*[_\(（]*\s*(Normal|Ranked|Casual|Competitive|Arcade|Event)\s*[_\)）]*\*{0,2}', line, re.IGNORECASE)
        if mode_match:
            raw_mode = mode_match.group(1)
            # 统一为英文模式名
            mode_map = {"单排": "Solo", "双排": "Duo", "四排": "Squad"}
            data["mode"] = mode_map.get(raw_mode, raw_mode)
            data["type"] = mode_match.group(2)
            continue
        
        # 排名: #7/16
        placement_match = re.match(r'#(\d+)\s*/\s*(\d+)', line)
        if placement_match:
            data["placement"] = int(placement_match.group(1))
            data["total_teams"] = int(placement_match.group(2))
            continue
        
        # 时间: Xh ago / Xd ago / Xm ago
        time_match = re.search(r'(\d+\s*(?:h|d|m|min)\s*ago)', line, re.IGNORECASE)
        if time_match:
            data["time_ago_text"] = time_match.group(1)
            data["approx_time"] = parse_time_ago(time_match.group(1), scrape_time)
            continue
        
        # 地图: "Map Karakin" (p1-3) 或 "Map\nRondo" (p4+)
        if line.startswith("Map "):
            map_name = line[4:].strip()
            data["map"] = map_name if map_name else None
            continue
        if line.strip() == "Map" and i + 1 < len(lines):
            map_name = lines[i + 1].strip()
            if map_name in MAP_NAMES or map_name == "Training Mode":
                data["map"] = map_name
            continue
        
        # 武器: "Weapon M416" (p1-3) 或 "Weapon\n-" (p4+)
        if line.startswith("Weapon "):
            wp = line[7:].strip()
            if wp and wp != "-":
                data["weapon"] = wp
            continue
        if line.strip() == "Weapon" and i + 1 < len(lines):
            wp = lines[i + 1].strip()
            if wp and wp != "-":
                data["weapon"] = wp
            continue
        
        # Kills: "Kills 2" or "Kills\n2"
        if line.startswith("Kills"):
            val = line.replace("Kills", "", 1).strip()
            if not val and i + 1 < len(lines):
                val = lines[i + 1]
            try:
                data["kills"] = int(val)
            except (ValueError, TypeError):
                pass
            continue
        
        # Damage: "Damage 204"
        if line.startswith("Damage"):
            val = line.replace("Damage", "", 1).strip()
            if not val and i + 1 < len(lines):
                val = lines[i + 1]
            try:
                data["damage"] = int(val.replace(",", ""))
            except (ValueError, TypeError, AttributeError):
                pass
            continue
        
        # DBNOs
        if line.startswith("DBNOs"):
            val = line.replace("DBNOs", "", 1).strip()
            if not val and i + 1 < len(lines):
                val = lines[i + 1]
            try:
                data["dbnos"] = int(val)
            except (ValueError, TypeError):
                pass
            continue
        
        # Traveled: "Traveled 2.59km"
        if line.startswith("Traveled"):
            val = line.replace("Traveled", "", 1).strip()
            if not val and i + 1 < len(lines):
                val = lines[i + 1]
            if val:
                data["traveled"] = val
            continue
        
        # Time Alive
        if line.startswith("Time Alive"):
            val = line.replace("Time Alive", "", 1).strip()
            if not val and i + 1 < len(lines):
                val = lines[i + 1]
            if val:
                data["time_alive"] = val
            continue
        
        # Longest (kill distance)
        if line.startswith("Longest"):
            val = line.replace("Longest", "", 1).strip()
            if not val and i + 1 < len(lines):
                val = lines[i + 1]
            if val:
                data["longest_kill"] = val
            continue
        
        # 队友链接: - [Name](url)
        teammate_match = re.match(r'-\s*\[([^\]]+)\]\([^)]+\)', line)
        if teammate_match:
            data["teammates"].append(teammate_match.group(1))
            continue
    
    return data


# ============================================================
# 数据统计
# ============================================================

def compute_stats(all_player_data, scrape_time):
    """计算每个玩家的统计数据"""
    stats = {}
    all_matches = []
    
    for steam_id, pdata in all_player_data.items():
        alias = pdata["alias"]
        matches = pdata.get("matches", [])
        
        if not matches:
            stats[steam_id] = _empty_stats(alias, steam_id)
            continue
        
        total_kills = sum(m.get("kills", 0) for m in matches)
        total_damage = sum(m.get("damage", 0) for m in matches)
        total_dbnos = sum(m.get("dbnos", 0) for m in matches)
        match_count = len(matches)
        
        chicken_dinners = sum(1 for m in matches if m.get("placement") == 1)
        top10 = sum(1 for m in matches if m.get("placement", 999) <= 10)
        
        # KDA: dak.gg 不直接显示死亡数，用排名估算
        estimated_deaths = sum(1 for m in matches if m.get("placement", 0) > 1)
        kda = round(total_kills / max(estimated_deaths, 1), 2)
        avg_kills = round(total_kills / match_count, 2)
        avg_damage = round(total_damage / match_count, 1)
        
        best_placement = min((m.get("placement", 999) for m in matches), default=999)
        
        # 地图/武器统计
        map_stats = defaultdict(int)
        weapon_stats = defaultdict(int)
        for m in matches:
            if m.get("map"):
                map_stats[m["map"]] += 1
            if m.get("weapon") and m["weapon"] not in ["-", "None", ""]:
                weapon_stats[m["weapon"]] += 1
        
        stats[steam_id] = {
            "alias": alias,
            "steam_id": steam_id,
            "match_count": match_count,
            "total_kills": total_kills,
            "total_damage": total_damage,
            "total_dbnos": total_dbnos,
            "kda": kda,
            "avg_kills": avg_kills,
            "avg_damage": avg_damage,
            "chicken_dinners": chicken_dinners,
            "chicken_rate": round(chicken_dinners / match_count * 100, 1),
            "top10_rate": round(top10 / match_count * 100, 1),
            "best_placement": best_placement,
            "map_stats": dict(map_stats),
            "weapon_stats": dict(weapon_stats),
        }
        
        for m in matches:
            m["player_alias"] = alias
            m["player_steam_id"] = steam_id
        all_matches.extend(matches)
    
    return stats, all_matches


def _empty_stats(alias, steam_id):
    return {
        "alias": alias, "steam_id": steam_id,
        "match_count": 0, "total_kills": 0, "total_damage": 0,
        "total_dbnos": 0, "kda": 0, "avg_kills": 0, "avg_damage": 0,
        "chicken_dinners": 0, "chicken_rate": 0, "top10_rate": 0,
        "best_placement": 999, "map_stats": {}, "weapon_stats": {},
    }


def compute_team_stats(all_matches, all_player_data):
    """计算队伍协作数据"""
    player_ids = set(all_player_data.keys())
    player_aliases = {pid: pd["alias"] for pid, pd in all_player_data.items()}
    
    combo_stats = defaultdict(lambda: {"games": 0, "chickens": 0, "placements": []})
    
    for match in all_matches:
        teammates = match.get("teammates", [])
        teammate_ids = set()
        for name in teammates:
            for sid, pd in all_player_data.items():
                if pd["alias"] == name or sid == name:
                    teammate_ids.add(sid)
        
        player_sid = match.get("player_steam_id", "")
        all_in_game = teammate_ids | {player_sid}
        
        placement = match.get("placement", 999)
        is_chicken = (placement == 1)
        
        ids_list = sorted(all_in_game)
        for i in range(len(ids_list)):
            for j in range(i + 1, len(ids_list)):
                pair = tuple(sorted([ids_list[i], ids_list[j]]))
                combo_stats[pair]["games"] += 1
                combo_stats[pair]["placements"].append(placement)
                if is_chicken:
                    combo_stats[pair]["chickens"] += 1
    
    combos = []
    for pair, cs in combo_stats.items():
        placements = cs["placements"]
        combos.append({
            "players": [{"steam_id": p, "alias": player_aliases.get(p, p)} for p in pair],
            "games": cs["games"],
            "chickens": cs["chickens"],
            "avg_placement": round(sum(placements) / len(placements), 1),
        })
    
    combos.sort(key=lambda x: x["games"], reverse=True)
    
    team_games = sum(1 for m in all_matches if len(set(
        t for t in m.get("teammates", []) 
        if any(t == pd["alias"] or t == sid for sid, pd in all_player_data.items())
    ) - {m.get("player_steam_id", "")}) >= 1)
    
    return {
        "team_games_count": team_games,
        "combos": combos,
    }


# ============================================================
# 称号和评语
# ============================================================

def clown_emoji():
    return random.choice(["🤡", "😅", "💩", "🤦", "😬"])


def generate_titles_and_comments(stats, team_stats):
    """生成有趣的称号和评语"""
    players = list(stats.values())
    if not players:
        return [], []
    
    titles = []
    comments = []
    
    active = [p for p in players if p["match_count"] > 0]
    
    if active:
        # 击杀王
        kill_king = max(active, key=lambda x: x["total_kills"])
        titles.append({
            "title": "🔫 击杀王",
            "player": kill_king["alias"],
            "value": f"{kill_king['total_kills']} 杀",
            "comment": f"枪管子都打冒烟了！{kill_king['alias']}的瞄准镜里全是人头。"
                       if kill_king['total_kills'] > 5
                       else f"勉强拿了个击杀王，但{clown_emoji()}这数据也好意思？"
        })
        
        # 伤害王
        dmg_king = max(active, key=lambda x: x["total_damage"])
        titles.append({
            "title": "💥 伤害王",
            "player": dmg_king["alias"],
            "value": f"{dmg_king['total_damage']:,} 伤害",
            "comment": f"每颗子弹都写着{random.choice(['尊重', '恐惧', '卧槽'])}！"
                       if dmg_king['total_damage'] > 500
                       else "这伤害量...打得挺热闹的，就是没打死人。"
        })
        
        # KDA之王
        kda_king = max(active, key=lambda x: x["kda"])
        titles.append({
            "title": "📈 KDA之王",
            "player": kda_king["alias"],
            "value": f"KDA {kda_king['kda']}",
            "comment": f"数据不会说谎——{kda_king['alias']}的KDA说明了一切。"
                       if kda_king['kda'] >= 2.0
                       else f"KDA {kda_king['kda']}...{clown_emoji()} 在玩跳伞模拟器？"
        })
        
        # 吃鸡王者
        chicken_king = max(active, key=lambda x: x["chicken_dinners"])
        if chicken_king["chicken_dinners"] > 0:
            titles.append({
                "title": "🍗 吃鸡王者",
                "player": chicken_king["alias"],
                "value": f"{chicken_king['chicken_dinners']} 次吃鸡",
                "comment": "Winner Winner Chicken Dinner! 🐔 鸡都吃撑了！"
                           if chicken_king['chicken_dinners'] >= 2
                           else "就吃了一次鸡，但也是鸡！比鸡屁股都没摸到的强。"
            })
        
        # 场均伤害王
        avg_dmg_king = max(active, key=lambda x: x["avg_damage"])
        titles.append({
            "title": "🎯 场均之王",
            "player": avg_dmg_king["alias"],
            "value": f"场均 {avg_dmg_king['avg_damage']} 伤害",
            "comment": "稳如老狗，每把都有稳定输出。"
                       if avg_dmg_king['avg_damage'] > 150
                       else f"场均{avg_dmg_king['avg_damage']}...打绷带都不止这么多。"
        })
        
        # 和平大使（0击杀但玩了很多场）
        if len(active) >= 2:
            kill_min = min(active, key=lambda x: x["total_kills"])
            if kill_min["total_kills"] == 0 and kill_min["match_count"] > 1:
                titles.append({
                    "title": "🕊️ 和平大使",
                    "player": kill_min["alias"],
                    "value": "0 击杀",
                    "comment": f"真正的和平主义者！{kill_min['alias']}：'我是来交朋友的'"
                })
        
        # 快递员
        if len(active) >= 2:
            kda_min = min(active, key=lambda x: x["kda"])
            if kda_min["kda"] < 0.5:
                titles.append({
                    "title": "💀 快递员",
                    "player": kda_min["alias"],
                    "value": f"KDA {kda_min['kda']}",
                    "comment": f"{kda_min['alias']}：'落地→搜装备→送快递→下一把'，物流行业标杆！"
                })
    
    # 最佳搭档
    combos = team_stats.get("combos", [])
    if combos:
        top = combos[0]
        names = [p["alias"] for p in top["players"]]
        titles.append({
            "title": "🤝 最佳搭档",
            "player": " & ".join(names),
            "value": f"{top['games']} 场同队",
            "comment": f"形影不离！{'和'.join(names)}简直是用502粘在一起了。"
                       if top['games'] >= 3
                       else "也就一起打了几把，别想太多。"
        })
    
    # ---- 个人评语 ----
    comment_templates = [
        ("{name}今天枪法如神，建议去参加职业联赛（认真脸）", lambda p: p.get("kda", 0) >= 3),
        ("{name}手感火热！保持了高水准发挥", lambda p: p.get("kda", 0) >= 2),
        ("{name}很稳，队友的坚实后盾 👍", lambda p: p.get("avg_damage", 0) >= 200),
        ("{name}吃鸡了！今晚可以吹一年 🍗", lambda p: p.get("chicken_dinners", 0) >= 2),
        ("{name}表现...建议去训练场多待会儿 😅", lambda p: p.get("kda", 0) < 0.5 and p.get("match_count", 0) > 0),
        ("{name}：我不是在送，我是在做慈善 🙏", lambda p: p.get("total_kills", 0) == 0 and p.get("match_count", 0) >= 2),
        ("{name}落地成盒专业户，跳伞姿势倒是挺帅的 ✈️", lambda p: p.get("avg_damage", 0) < 50 and p.get("match_count", 0) > 0),
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


# ============================================================
# HTML 报告生成（紧凑单屏版）
# ============================================================

def generate_html_report(stats, team_stats, titles, comments, time_start, time_end, generated_at):
    """生成手机竖屏领奖台版 HTML 战报"""
    date_str = time_start.strftime("%Y年%m月%d日")
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    friendly_date = f"📅 {time_start.year}年{time_start.month:02d}月{time_start.day:02d}日 {weekdays[time_start.weekday()]}"

    # ── 排序：出战优先 > 击杀数 > 伤害 ──
    sorted_players = sorted(
        stats.values(),
        key=lambda x: (x["match_count"] > 0, x["total_kills"], x["total_damage"]),
        reverse=True,
    )

    def card_class(p):
        if p["match_count"] == 0: return "card-absent"
        if p["kda"] >= 2.5: return "card-god"
        if p["kda"] >= 1.5: return "card-good"
        if p["kda"] >= 0.8: return "card-avg"
        return "card-bad"

    def make_card(p, rank_label):
        best = f"#{p['best_placement']}" if p['best_placement'] != 999 else "-"
        kda_class = "clr-gold" if p['kda'] >= 2 else ("clr-red" if p['kda'] < 0.8 else "")
        maps_html = "".join(
            f"<i>{MAP_ZH.get(m, m)}</i>" for m, c in sorted(p.get("map_stats", {}).items(), key=lambda x: -x[1])[:3]
        ) if p.get("map_stats") else ""
        return f"""<article class="pcard {card_class(p)}">
        <div class="pc-head">
          <div class="pc-player"><div class="pc-rank" aria-hidden="true">{rank_label}</div><div class="pc-identity"><div class="pc-name">{p['alias']}</div><div class="pc-sub">{p['match_count']} 场作战</div></div></div>
          <div class="pc-kills"><strong>{p['total_kills']}</strong><span>击杀</span></div>
        </div>
        <div class="pc-metrics">
          <div><span>总伤害</span><b>{p['total_damage']:,}</b></div>
          <div><span>KDA</span><b class="{kda_class}">{p['kda']}</b></div>
          <div><span>吃鸡</span><b>🍗 × {p['chicken_dinners']}</b></div>
          <div><span>场均击杀</span><b>{p['avg_kills']}</b></div>
          <div><span>场均伤害</span><b>{p['avg_damage']:.0f}</b></div>
          <div><span>最佳排名</span><b>{best}</b></div>
        </div>
        {f'<div class="pc-tags">{maps_html}</div>' if maps_html else ''}
        </article>"""

    def make_table_row(p, rank_label):
        best = f"#{p['best_placement']}" if p['best_placement'] != 999 else "-"
        kda_class = "clr-gold" if p['kda'] >= 2 else ("clr-red" if p['kda'] < 0.8 else "")
        return f"""<tr class="{card_class(p)}">
          <th scope="row"><span class="pt-rank">{rank_label}</span><strong>{p['alias']}</strong><small>{p['match_count']}场</small></th>
          <td class="pt-kills">{p['total_kills']}</td>
          <td>{p['total_damage']:,}</td>
          <td class="{kda_class}">{p['kda']}</td>
          <td>{p['avg_kills']}/{p['avg_damage']:.0f}</td>
          <td>🍗{p['chicken_dinners']}</td>
          <td>{best}</td>
        </tr>"""

    # ── 领奖台: [亚军左] [冠军中] [季军右] ──
    # 领奖台只包含实际出战的人（未出战不参与排名，空位留白）
    active_players = [p for p in sorted_players if p["match_count"] > 0]
    podium = active_players[:3]  # 最多前3名出战玩家
    podium_order = [
        podium[1] if len(podium) > 1 else None,  # 亚军 (左)
        podium[0] if len(podium) > 0 else None,  # 冠军 (中)
        podium[2] if len(podium) > 2 else None,  # 季军 (右)
    ]
    podium_labels = ["🥈", "👑", "🥉"]
    podium_html = ""
    for i, p in enumerate(podium_order):
        if p:
            podium_html += make_card(p, podium_labels[i])
        else:
            # 空位占位，保持领奖台三列布局
            podium_html += '<div style="min-height:0;opacity:0;pointer-events:none"></div>'

    # ── 剩余玩家：未出战 + 出战但没进前3的 ──
    podium_ids = {id(p) for p in podium if p}
    rest = [p for p in sorted_players if id(p) not in podium_ids]
    rest_labels = ["4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
    rest_html = ""
    for i, p in enumerate(rest):
        rest_html += make_table_row(p, rest_labels[i] if i < len(rest_labels) else "")

    # ── 称号 ──
    titles_html = "".join(
        f"""<span class="tl-badge">
          <b>{t['title']}</b> {t['player']} · {t['value']}
          <small>——{t['comment']}</small>
        </span>"""
        for t in titles
    )

    # ── 评语 ──
    comments_html = "".join(f"<li>{c}</li>" for c in comments)

    # ── 搭档 ──
    combos = team_stats.get("combos", [])[:3]
    combos_html = " · ".join(
        f"<b>{' + '.join(p['alias'] for p in c['players'])}</b> {c['games']}场🍗x{c['chickens']}"
        for c in combos
    ) if combos else "昨天各玩各的 🥲"

    # ── 汇总 ──
    total_matches = sum(p['match_count'] for p in stats.values())
    total_kills = sum(p['total_kills'] for p in stats.values())
    total_chickens = sum(p['chicken_dinners'] for p in stats.values())
    total_damage = sum(p['total_damage'] for p in stats.values())
    active_count = sum(1 for p in stats.values() if p['match_count'] > 0)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#0b0d0c">
<title>PUBG战报·{date_str}</title>
<script>if(new URLSearchParams(location.search).has('capture'))document.documentElement.classList.add('capture')</script>
<style>
:root{{--bg:#070908;--panel:#101411;--panel-2:#151a16;--line:rgba(255,255,255,.12);--muted:#aab2aa;--text:#f7f9f5;--gold:#f5b82e;--gold-2:#ffda69;--green:#b7da89;--red:#ff8178}}
*{{margin:0;padding:0;box-sizing:border-box}}
html{{background:#050706}}
body{{min-height:100vh;padding:24px 14px;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:var(--text);background:radial-gradient(circle at 50% -20%,#27301f 0,transparent 42%),#050706}}
.page{{position:relative;width:100%;max-width:760px;min-height:100vh;margin:auto;overflow:hidden;border:1px solid rgba(245,184,46,.18);border-radius:22px;background:linear-gradient(180deg,rgba(18,22,18,.98),rgba(7,9,8,.99));box-shadow:0 28px 90px rgba(0,0,0,.6)}}
.page::before{{content:"";position:absolute;inset:0;pointer-events:none;opacity:.18;background-image:linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px);background-size:28px 28px;mask-image:linear-gradient(to bottom,#000,transparent 38%)}}
.page>*{{position:relative}}

/* ── 战报头部 ── */
.topbar{{padding:30px 28px 26px;border-bottom:1px solid var(--line);background:radial-gradient(circle at 82% 0,rgba(245,184,46,.16),transparent 32%),linear-gradient(135deg,rgba(255,255,255,.045),transparent 60%)}}
.topline{{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}}
.kicker{{color:var(--gold);font-size:10px;font-weight:800;letter-spacing:2.2px}}
.edition{{padding:3px 8px;border:1px solid rgba(245,184,46,.38);border-radius:999px;color:var(--gold-2);font-size:9px;font-weight:800;letter-spacing:1.4px}}
.title-wrap{{display:flex;align-items:center;gap:14px}}
.hero-row{{display:flex;align-items:flex-end;justify-content:space-between;gap:20px}}
.title-mark{{display:grid;width:44px;height:44px;place-items:center;border:1px solid rgba(245,184,46,.5);border-radius:12px;color:#111;background:linear-gradient(145deg,var(--gold-2),#cc8612);font-size:20px;box-shadow:0 8px 24px rgba(245,184,46,.16);transform:skew(-5deg)}}
.topbar h1{{font-size:36px;font-weight:900;line-height:1.05;letter-spacing:-1px}}
.topbar h1 span{{color:var(--gold);letter-spacing:1px}}
.subtitle{{margin-top:5px;color:#b0b9b0;font-size:12px;letter-spacing:1.6px;text-transform:uppercase}}
.topbar .info{{display:flex;flex:0 0 auto;flex-direction:column;align-items:flex-end;gap:5px;padding:4px 12px;border:1px solid rgba(245,184,46,.12);border-radius:10px;background:rgba(245,184,46,.04)}}
.topbar .info-date{{font-size:14px;color:var(--gold);font-weight:700;letter-spacing:.5px;white-space:nowrap}}
.topbar .info-range{{font-size:13px;color:#b3bfb3;letter-spacing:.2px}}
.topbar .info-count{{font-size:12px;color:#97a397}}
.topbar .info-count b{{color:var(--gold-2);font-weight:800}}

/* ── 核心数据 ── */
.nums{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;padding:16px 18px 2px}}
.num-item{{min-width:0;padding:12px 8px;border:1px solid rgba(255,255,255,.065);border-radius:10px;text-align:center;background:linear-gradient(180deg,rgba(255,255,255,.045),rgba(255,255,255,.018))}}
.num-item .n{{display:block;overflow:hidden;color:var(--gold-2);font-size:26px;font-weight:900;line-height:1.1;letter-spacing:-.4px;text-overflow:ellipsis}}
.num-item .l{{display:block;margin-top:6px;color:var(--muted);font-size:12px;font-weight:800;letter-spacing:.5px;white-space:nowrap}}

/* ── 区块标题 ── */
.section-title{{display:flex;align-items:center;gap:10px;margin:28px 20px 12px;color:#f1f4ee;font-size:18px;font-weight:900;letter-spacing:.8px}}
.section-title::after{{content:"";height:1px;flex:1;background:linear-gradient(90deg,rgba(245,184,46,.35),transparent)}}

/* ── 选手卡片 ── */
.podium{{display:grid;grid-template-columns:repeat(3,1fr);align-items:end;gap:10px;padding:0 18px}}
.pcard{{position:relative;min-width:0;overflow:hidden;padding:17px 14px 13px;border:1px solid var(--line);border-radius:14px;background:linear-gradient(145deg,rgba(255,255,255,.055),rgba(255,255,255,.018));box-shadow:0 10px 24px rgba(0,0,0,.18)}}
.pcard::before{{content:"";position:absolute;inset:0 0 auto;height:2px;background:#727a72;opacity:.55}}
.pcard.card-god{{border-color:rgba(245,184,46,.3);background:linear-gradient(145deg,rgba(245,184,46,.12),rgba(255,255,255,.018))}}
.pcard.card-god::before{{background:var(--gold)}}
.pcard.card-good{{border-color:rgba(157,197,110,.23);background:linear-gradient(145deg,rgba(157,197,110,.09),rgba(255,255,255,.018))}}
.pcard.card-good::before{{background:var(--green)}}
.pcard.card-bad{{border-color:rgba(239,106,98,.22);background:linear-gradient(145deg,rgba(239,106,98,.08),rgba(255,255,255,.018))}}
.pcard.card-bad::before{{background:var(--red)}}
.pcard.card-absent{{filter:saturate(.2);opacity:.48}}
.podium .pcard:nth-child(1){{border-color:rgba(205,214,220,.24)}}
.podium .pcard:nth-child(1)::before{{background:#cbd4d8}}
.podium .pcard:nth-child(2){{padding-top:17px;border-color:rgba(245,184,46,.48);background:radial-gradient(circle at 50% 0,rgba(245,184,46,.2),transparent 48%),linear-gradient(145deg,#222015,#11140f);box-shadow:0 16px 38px rgba(0,0,0,.3),0 0 26px rgba(245,184,46,.08);transform:translateY(-6px)}}
.podium .pcard:nth-child(2)::before{{height:3px;background:linear-gradient(90deg,#b8750c,var(--gold-2),#b8750c);opacity:1}}
.podium .pcard:nth-child(3){{border-color:rgba(205,127,50,.25)}}
.podium .pcard:nth-child(3)::before{{background:#cd7f32}}
.pc-head{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);align-items:center}}
.pc-player{{display:flex;min-width:0;align-items:center;gap:9px}}
.pc-rank{{flex:0 0 auto;font-size:28px;line-height:1;filter:drop-shadow(0 3px 5px rgba(0,0,0,.35))}}
.pc-identity{{min-width:0;flex:1}}
.pc-name{{overflow:hidden;color:#fff;font-size:20px;font-weight:900;line-height:1.15;white-space:nowrap;text-overflow:ellipsis}}
.pc-sub{{margin-top:5px;color:#b9c1b9;font-size:12px;font-weight:700;letter-spacing:.4px}}
.pc-kills{{display:flex;min-width:0;flex-direction:column;align-items:center;justify-self:stretch;line-height:1;text-align:center}}
.pc-kills strong{{color:var(--gold-2);font-size:30px;font-weight:900;letter-spacing:-1px}}
.pc-kills span{{margin-top:4px;color:#c0c7c0;font-size:11px;font-weight:800;letter-spacing:1px}}
.pc-metrics{{display:grid;grid-template-columns:repeat(3,1fr);margin-top:13px;border-top:1px solid rgba(255,255,255,.07);border-left:1px solid rgba(255,255,255,.07)}}
.pc-metrics div{{min-width:0;padding:9px 3px 8px;border-right:1px solid rgba(255,255,255,.07);border-bottom:1px solid rgba(255,255,255,.07);text-align:center}}
.pc-metrics span,.pc-metrics b{{display:block;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}}
.pc-metrics span{{color:#b8c0b8;font-size:11px;font-weight:700}}
.pc-metrics b{{margin-top:4px;color:#fff;font-size:15px;font-weight:900}}
.pc-metrics .clr-gold{{color:var(--gold-2)}}
.pc-metrics .clr-red{{color:var(--red)}}
.pc-tags{{display:flex;align-items:center;gap:5px;overflow:hidden;margin-top:11px;white-space:nowrap}}
.pc-tags span{{flex:0 0 auto;color:#b2bbb2;font-size:10px;font-weight:700}}
.pc-tags i{{overflow:hidden;padding:3px 7px;border:1px solid rgba(245,184,46,.22);border-radius:999px;color:#f2c65a;background:rgba(245,184,46,.08);font-size:10px;font-style:normal;text-overflow:ellipsis}}

/* 其他选手：表格展示，每位选手严格占一行 */
.player-table-wrap{{padding:0 18px}}
.player-table{{width:100%;table-layout:fixed;border-spacing:0 9px;font-size:13px;text-align:center}}
.player-table th,.player-table td{{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}}
.player-table thead th{{padding:0 3px 4px;color:#c4ccc4;font-size:10px;font-weight:900;letter-spacing:.3px}}
.player-table thead th:first-child{{width:25%;text-align:left;padding-left:10px}}
.player-table thead th:nth-child(2){{width:10%}}
.player-table thead th:nth-child(3){{width:16%}}
.player-table thead th:nth-child(4){{width:11%}}
.player-table thead th:nth-child(5){{width:17%}}
.player-table thead th:nth-child(6){{width:11%}}
.player-table thead th:nth-child(7){{width:10%}}
.player-table tbody th,.player-table tbody td{{height:50px;padding:8px 3px;border-top:1px solid rgba(255,255,255,.09);border-bottom:1px solid rgba(255,255,255,.09);color:#fff;background:rgba(255,255,255,.03)}}
.player-table tbody th{{padding-left:8px;border-left:1px solid rgba(255,255,255,.065);border-radius:9px 0 0 9px;text-align:left}}
.player-table tbody td:last-child{{border-right:1px solid rgba(255,255,255,.065);border-radius:0 9px 9px 0}}
.player-table tbody tr.card-good th,.player-table tbody tr.card-good td{{background:rgba(157,197,110,.045)}}
.player-table tbody tr.card-bad th,.player-table tbody tr.card-bad td{{background:rgba(239,106,98,.04)}}
.player-table tbody tr.card-absent{{opacity:.42}}
.player-table .pt-rank{{margin-right:5px;font-size:15px;vertical-align:middle}}
.player-table tbody th strong{{color:#fff;font-size:14px}}
.player-table tbody th small{{margin-left:4px;color:#b6beb6;font-size:10px;font-weight:700}}
.player-table .pt-kills{{color:var(--gold-2);font-size:21px;font-weight:900}}
.player-table .clr-gold{{color:var(--gold-2)}}
.player-table .clr-red{{color:var(--red)}}

/* ── 荣誉与锐评 ── */
.honors,.comments{{padding:0 18px}}
.tl-list,.cmt-list{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}}
.tl-badge{{position:relative;display:block;min-width:0;padding:14px 15px 13px 18px;border:1px solid rgba(255,255,255,.09);border-radius:10px;background:rgba(255,255,255,.03);font-size:16px;color:#f2f5f0}}
.tl-badge::before{{content:"";position:absolute;left:0;top:11px;width:3px;height:18px;border-radius:0 3px 3px 0;background:var(--gold)}}
.tl-badge b{{color:var(--gold-2)}}
.tl-badge small{{display:block;margin-top:6px;color:#c4ccc4;font-size:13px;font-style:normal;line-height:1.45}}
.cmt-list{{list-style:none}}
.cmt-list li{{position:relative;padding:13px 15px 13px 34px;border:1px solid rgba(255,255,255,.08);border-radius:10px;color:#f0f3ee;background:rgba(255,255,255,.025);font-size:15px}}
.cmt-list li::before{{content:"“";position:absolute;left:10px;top:5px;color:var(--gold);font:700 22px/1 Georgia,serif}}

/* ── 搭档与页脚 ── */
.partner-bar{{margin:22px;padding:15px 18px;border:1px solid rgba(245,184,46,.2);border-radius:12px;color:#e0e5df;background:linear-gradient(90deg,rgba(245,184,46,.07),rgba(255,255,255,.025));font-size:15px;text-align:center}}
.partner-bar b{{color:var(--gold-2)}}
.foot{{margin-top:4px;padding:17px 16px 22px;border-top:1px solid rgba(255,255,255,.06);color:#b3bbb3;font-size:12px;letter-spacing:.35px;text-align:center}}
.capture,.capture body{{min-height:0;background:#000}}
.capture .page{{min-height:0}}

@media (prefers-reduced-motion:reduce){{*{{scroll-behavior:auto!important}}}}
</style></head>
<body>
<main class="page">
<header class="topbar">
  <div class="topline"><span class="kicker">BATTLEGROUND INTELLIGENCE</span><span class="edition">DAILY</span></div>
  <div class="hero-row">
    <div class="title-wrap"><div class="title-mark" aria-hidden="true">▰</div><div><h1><span>PUBG</span> 每日战报</h1><div class="subtitle">Survival performance report</div></div></div>
    <div class="info"><div class="info-date">{friendly_date}</div><div class="info-range">{time_start.strftime('%H:%M')} — 次日 {time_end.strftime('%H:%M')}</div><div class="info-count"><b>{active_count}/{len(stats)}</b> 人出战</div></div>
  </div>
</header>
<section class="nums" aria-label="战队核心数据">
  <div class="num-item"><span class="n">{total_matches}</span><span class="l">总场次</span></div>
  <div class="num-item"><span class="n">{total_kills}</span><span class="l">总击杀</span></div>
  <div class="num-item"><span class="n">{total_damage:,}</span><span class="l">总伤害</span></div>
  <div class="num-item"><span class="n">{total_chickens}</span><span class="l">吃鸡🍗</span></div>
  <div class="num-item"><span class="n">{round(total_kills/max(active_count,1),1)}</span><span class="l">人均击杀</span></div>
  <div class="num-item"><span class="n">{round(total_damage/max(active_count,1)):,}</span><span class="l">人均伤害</span></div>
</section>

<h2 class="section-title">🏆 领奖台</h2>
<div class="podium">{podium_html}</div>

{f'<h2 class="section-title">👥 其他选手</h2><div class="player-table-wrap"><table class="player-table"><thead><tr><th>选手</th><th>击杀</th><th>伤害</th><th>KDA</th><th>场均 杀/伤</th><th>吃鸡</th><th>最佳</th></tr></thead><tbody>{rest_html}</tbody></table></div>' if rest_html else ''}

<h2 class="section-title">🎖️ 荣誉称号</h2>
<div class="honors"><div class="tl-list">{titles_html}</div></div>

<h2 class="section-title">📝 小编锐评</h2>
<div class="comments"><ul class="cmt-list">{comments_html}</ul></div>

<div class="partner-bar">🤝 最佳搭档：{combos_html}</div>
<div class="foot">📊 DAK.GG · {generated_at.strftime('%Y-%m-%d %H:%M')} · 大吉大利今晚吃鸡</div>
</main>
</body></html>"""


# ============================================================
# PNG 截图生成
# ============================================================

def _find_chrome():
    """查找可用于无头截图的 Chrome/Chromium。"""
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise FileNotFoundError("未找到 Google Chrome 或 Chromium，无法生成 PNG 截图")


def generate_report_screenshot(html_path, png_path, max_height=6000):
    """按 760px 宽度用 Chrome 渲染战报，裁掉页面外空白。"""
    try:
        from PIL import Image, ImageChops
    except ImportError as exc:
        raise RuntimeError("生成截图需要 Pillow：pip install Pillow") from exc

    html_path = Path(html_path).resolve()
    png_path = Path(png_path).resolve()
    chrome = _find_chrome()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    width = 760

    with tempfile.TemporaryDirectory(prefix="pubg_capture_") as temp_dir:
        temp_dir = Path(temp_dir)
        raw_path = temp_dir / "raw.png"
        profile_path = temp_dir / "chrome_profile"
        render_width = width + 28
        capture_url = f"{html_path.as_uri()}?capture=1"
        command = [
            chrome,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-sync",
            "--hide-scrollbars",
            "--no-default-browser-check",
            "--no-first-run",
            "--force-device-scale-factor=1",
            f"--user-data-dir={profile_path}",
            f"--window-size={render_width},{max_height}",
            f"--screenshot={raw_path}",
            capture_url,
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        screenshot_ready = False
        last_size = -1
        stable_checks = 0
        deadline = time.monotonic() + 30
        try:
            while time.monotonic() < deadline:
                if raw_path.exists():
                    current_size = raw_path.stat().st_size
                    if current_size > 0 and current_size == last_size:
                        stable_checks += 1
                        if stable_checks >= 2:
                            screenshot_ready = True
                            break
                    else:
                        stable_checks = 0
                        last_size = current_size
                if process.poll() is not None and not raw_path.exists():
                    break
                time.sleep(0.2)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

        if not screenshot_ready:
            raise RuntimeError("Chrome 截图超时或未生成图片")

        with Image.open(raw_path) as image:
            image = image.convert("RGB")
            black = Image.new("RGB", image.size, (0, 0, 0))
            content_box = ImageChops.difference(image, black).getbbox()
            if not content_box:
                raise RuntimeError("Chrome 截图为空白")
            content_left = content_box[0]
            content_right = content_box[2]
            content_bottom = min(content_box[3] + 1, image.height)
            if content_bottom >= image.height - 2:
                raise RuntimeError(f"页面高度超过截图上限 {max_height}px")
            cropped = image.crop((content_left, 0, content_right, content_bottom))
            if cropped.width != width:
                raise RuntimeError(f"截图宽度异常：期望 {width}px，实际 {cropped.width}px")
            cropped.save(png_path, optimize=True)

    return png_path


def regenerate_screenshot(html_path, png_path):
    """仅为已有 HTML 重新生成截图。"""
    return generate_report_screenshot(html_path, png_path)


# ============================================================
# 数据覆盖自检
# ============================================================

def scan_data_coverage(data_dir, players, now):
    """快速扫描每个玩家 raw 文件的时间覆盖范围，判断数据是否完整。

    返回 {steam_id: {alias, earliest, latest, pages, total_matches}}
    earliest/latest 为 datetime 或 None。
    """
    month_map = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }

    coverage = {}
    for player in players:
        steam_id = player["steam_id"]
        alias = player["alias"]
        raw_files = sorted(data_dir.glob(f"{steam_id}_raw*.txt"))

        if not raw_files:
            coverage[steam_id] = {"alias": alias, "earliest": None, "latest": None, "pages": 0, "total_matches": 0}
            continue

        all_text = "\n".join(f.read_text(encoding="utf-8") for f in raw_files)
        times = []

        # 1) 相对时间: "10h ago", "3d ago"
        for m in re.finditer(r'(\d+)\s*(h|d)\s+ago', all_text):
            val, unit = int(m.group(1)), m.group(2)
            if unit == "h":
                times.append(now - timedelta(hours=val))
            else:
                times.append(now - timedelta(days=val))

        # 2) 绝对日期 (dak.gg 旧数据): "Jul 11"
        for m in re.finditer(r'"([A-Z][a-z]{2})\s+(\d{1,2})"', all_text):
            month_str, day = m.group(1), int(m.group(2))
            month = month_map.get(month_str)
            if month:
                year = now.year
                # 如果月份 > 当前月份，说明是上一年的数据
                if month > now.month:
                    year -= 1
                times.append(datetime(year, month, day, 12, 0))

        if times:
            coverage[steam_id] = {
                "alias": alias,
                "earliest": min(times),
                "latest": max(times),
                "pages": len(raw_files),
                "total_matches": len(times),
            }
        else:
            coverage[steam_id] = {"alias": alias, "earliest": None, "latest": None, "pages": len(raw_files), "total_matches": 0}

    return coverage


def check_and_warn_coverage(coverage, players, target_start, target_end):
    """检查每个玩家数据是否覆盖到目标时段，打印警告并返回缺失信息。

    返回: {steam_id: {needs_pages, gap_days}} — 空字典表示全部完整。
    """
    gaps = {}
    for player in players:
        steam_id = player["steam_id"]
        alias = player["alias"]
        cov = coverage[steam_id]

        if cov["earliest"] is None:
            if cov["pages"] == 0:
                print(f"  ❌ {alias}: 无数据文件，无法生成报告")
                gaps[steam_id] = {"needs_pages": "?", "gap_days": "?"}
            else:
                print(f"  ⚠️  {alias}: 有 {cov['pages']} 页数据但无法提取时间，请检查 raw 文件")
            continue

        # 判断：数据最早时间是否 <= 目标时段结束
        if cov["earliest"] > target_end:
            gap = cov["earliest"] - target_end
            gap_days = max(gap.days, 1)
            # 估算需要多少页（每页约 10 场比赛，假设该玩家每天 N 场）
            avg_per_day = max(cov["total_matches"] / max((cov["latest"] - cov["earliest"]).days, 1), 1)
            est_pages = max(int(gap_days * avg_per_day / 10) + 1, 1)
            print(f"  ⚠️  {alias}: 数据不足！最早记录={cov['earliest'].strftime('%m/%d')}，"
                  f"目标时段={target_start.strftime('%m/%d')}~{target_end.strftime('%m/%d')}，"
                  f"缺约{gap_days}天，需拉取 ≈{est_pages} 页")
            gaps[steam_id] = {"needs_pages": est_pages, "gap_days": gap_days}
        else:
            print(f"  ✅ {alias}: 覆盖完整（{cov['pages']}页{cov['total_matches']}场，"
                  f"{cov['earliest'].strftime('%m/%d')}~{cov['latest'].strftime('%m/%d')}）")

    return gaps


# ============================================================
# 主流程
# ============================================================

def run(days_ago=1):
    """主入口：从 data/*.txt 文件读取 WebFetch 数据并生成战报
    days_ago=1: 昨天; days_ago=2: 前天; ...
    """
    print("=" * 60)
    print("🎮 PUBG 每日战报生成器 v2.0")
    print("=" * 60)
    
    def json_serial(obj):
        """JSON 序列化辅助：处理 datetime"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")
    
    # 1. 加载配置
    with open(CONF_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    players = config["players"]
    print(f"✅ 加载 {len(players)} 位玩家配置")
    
    # 2. 时间范围
    time_start, time_end, now = get_time_range(days_ago)
    print(f"\n📅 数据时段: {time_start.strftime('%Y-%m-%d %H:%M')} ~ {time_end.strftime('%Y-%m-%d %H:%M')}")

    # 2.5 数据覆盖自检（在解析前快速扫描）
    print(f"\n🔍 数据覆盖自检：")
    coverage = scan_data_coverage(DATA_DIR, players, now)
    gaps = check_and_warn_coverage(coverage, players, time_start, time_end)

    if gaps:
        print(f"\n{'─' * 50}")
        print(f"💡 以上玩家数据不足，建议拉取以下分页后重跑：")
        for steam_id, info in gaps.items():
            alias = coverage[steam_id]["alias"]
            next_page = coverage[steam_id]["pages"] + 1
            pages_needed = info["needs_pages"]
            # 给出具体页面号
            last_page = coverage[steam_id]["pages"]
            urls = " ".join(
                f"page{p}"
                for p in range(next_page, next_page + min(pages_needed if isinstance(pages_needed, int) else 2, 5))
            )
            print(f"   {alias}: 已有{last_page}页 → 需 {urls}")
        print(f"{'─' * 50}\n")

    # 3. 读取原始数据文件
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    
    all_player_data = {}
    
    for player in players:
        alias = player["alias"]
        steam_id = player["steam_id"]
        
        # 读取所有原始数据文件（支持多页: {steam_id}_raw.txt, {steam_id}_raw_2.txt, ...）
        raw_files = sorted(DATA_DIR.glob(f"{steam_id}_raw*.txt"))
        
        if not raw_files:
            print(f"⚠️  {alias}: 未找到数据文件")
            all_player_data[steam_id] = {"alias": alias, "steam_id": steam_id, "matches": []}
            continue
        
        # 合并所有页面数据
        raw_text = "\n".join(f.read_text(encoding="utf-8") for f in raw_files)
        matches = parse_dakgg_markdown(raw_text, alias, now, time_start, time_end, config)
        
        print(f"✅ {alias}: 解析到 {len(matches)} 场时段内比赛")
        all_player_data[steam_id] = {
            "alias": alias,
            "steam_id": steam_id,
            "matches": matches,
        }
        
        # 保存解析后的结构化数据
        parsed_file = DATA_DIR / f"{steam_id}_parsed.json"
        with open(parsed_file, "w", encoding="utf-8") as f:
            json.dump(all_player_data[steam_id], f, ensure_ascii=False, indent=2, default=json_serial)
    
    # 4. 计算统计
    stats, all_matches = compute_stats(all_player_data, now)
    team_stats = compute_team_stats(all_matches, all_player_data)
    
    # 5. 称号 & 评语
    titles, comments = generate_titles_and_comments(stats, team_stats)
    
    # 6. 生成 HTML
    html = generate_html_report(stats, team_stats, titles, comments, time_start, time_end, now)
    
    # 7. 保存
    date_str = time_start.strftime("%Y%m%d")
    report_path = REPORT_DIR / f"pubg_report_{date_str}.html"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(html, encoding="utf-8")
    
    # 8. 生成 PNG 截图
    screenshot_path = report_path.with_suffix(".png")
    try:
        generate_report_screenshot(report_path, screenshot_path)
        print(f"📸 战报截图已生成: {screenshot_path}")
    except Exception as exc:
        print(f"⚠️  战报截图生成失败: {exc}")

    # 仅当天（昨天）的报告更新 latest 文件，历史报告不覆盖
    if days_ago == 1:
        latest_path = REPORT_DIR / "latest.html"
        latest_path.write_text(html, encoding="utf-8")
        if screenshot_path.exists():
            latest_screenshot = REPORT_DIR / "latest.png"
            shutil.copyfile(screenshot_path, latest_screenshot)
        print(f"📌 已同步 latest.html / latest.png")

    # 9. 保存统计JSON
    stats_json = DATA_DIR / f"stats_{date_str}.json"
    with open(stats_json, "w", encoding="utf-8") as f:
        json.dump({
            "date": date_str,
            "time_start": time_start.isoformat(),
            "time_end": time_end.isoformat(),
            "generated_at": now.isoformat(),
            "stats": {k: {kk: vv for kk, vv in v.items() if kk not in ["map_stats", "weapon_stats"]} 
                       for k, v in stats.items()},
            "team_stats": team_stats,
            "titles": titles,
        }, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 战报生成完成: {report_path}")
    return str(report_path)


if __name__ == "__main__":
    import sys
    days_ago = 1
    for arg in sys.argv[1:]:
        if arg.startswith("--days-ago="):
            days_ago = int(arg.split("=")[1])
    report = run(days_ago=days_ago)
    print(f"🎉 完成！战报路径: {report}")
