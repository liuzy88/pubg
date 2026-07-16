#!/usr/bin/env python3
"""
fetch_data.py — CentOS 端独立数据采集脚本

从 dak.gg 抓取 PUBG 比赛数据，输出格式与 WebFetch 一致，
供 pubg_daily_report.py 直接解析。

用法:
    python3 fetch_data.py              # 采集所有玩家 page_count 页
    python3 fetch_data.py --player zhong8yang8  # 只采集单个玩家
    python3 fetch_data.py --pages 5    # 指定页数

依赖:
    pip3 install requests beautifulsoup4
"""

import json
import re
import sys
import time
import argparse
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("请先安装: pip3 install requests beautifulsoup4")

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("请先安装: pip3 install beautifulsoup4")


BASE_URL = "https://dak.gg/pubg/profile/steam/{steam_id}/pc-2018-42/matches"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
    "Cache-Control": "no-cache",
}


def fetch_player_page(steam_id: str, page: int = 1) -> str:
    """
    抓取单个玩家的一页数据。

    返回与 WebFetch 输出格式一致的纯文本：
    - 模式: **Squad _(Normal)_**
    - 排名: #7/16
    - 时间: 15h ago
    - Map / Kills / Damage 等字段分行
    - 每个 match 以 More 结尾
    """
    url = BASE_URL.format(steam_id=steam_id)
    if page > 1:
        url += f"/{page}"

    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 404:
        return ""  # 页面不存在，无更多数据
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── 清理 HTML → 结构化纯文本 ──
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript",
                     "svg", "img", "canvas", "iframe", "link", "meta"]):
        tag.decompose()

    # 获取带换行的文本（保留 HTML 元素间的自然换行）
    text = soup.get_text("\n", strip=True)

    # ── 格式归一化 ──

    # 1. 合并多个空行 → 最多两个空行
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    # 2. 模式行：Squad (Normal) / Solo (Normal) 等 → **Squad _(Normal)_**
    #    处理 HTML 中 <strong>Squad <em>(Normal)</em></strong> 拆成两行的情况
    mode_pattern = re.compile(
        r"\b(Squad|Duo|Solo|1-Man Squad)\s*[\(（]\s*(Normal|Ranked|Casual|Arcade|Event)\s*[\)）]",
        re.IGNORECASE
    )
    text = mode_pattern.sub(r"**\1 _(\2)_**", text)

    # 3. 关键字段行规范化：确保 Map/Weapon 等后面跟着值而非空行
    _KEY_FIELDS = ["Map", "Weapon", "Kills", "Damage", "DBNOs",
                   "Traveled", "Time Alive", "Longest"]
    for kw in _KEY_FIELDS:
        # 把独立的 "Map\n" 行和 "Karakin\n" 行保持在一起
        # 不额外加空行，保持原有格式
        pass

    # 4. "More" 链接 → 统一为单独的 "More" 行
    text = re.sub(r"\n\s*More\s*\n", "\nMore\n", text)

    # 5. 去掉 dak.gg 页面顶部/底部的无关文本（保留关键区域）
    lines = text.split("\n")
    cleaned = []
    in_match = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue

        # 检测 match 开始标记
        if stripped.startswith("**") and "_(" in stripped:
            in_match = True

        if in_match:
            cleaned.append(stripped)
        elif re.match(r"^#\d+/\d+$", stripped):
            # 排名行也在 match 区域内
            in_match = True
            cleaned.append(stripped)

    # 如果没找到 structured matches，保留全部文本
    result = "\n".join(cleaned) if cleaned else text

    # 最终清理：去掉连续三个以上空行
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


def main():
    parser = argparse.ArgumentParser(description="PUBG 数据采集")
    parser.add_argument("--player", help="只采集指定 steam_id")
    parser.add_argument("--pages", type=int, help="采集页数（覆盖 conf.json 中的 page_count）")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    conf = json.loads((script_dir / "conf.json").read_text())
    data_dir = script_dir / "data"
    data_dir.mkdir(exist_ok=True)

    page_count = args.pages or conf["dakgg"]["page_count"]
    players = conf["players"]

    if args.player:
        players = [p for p in players if p["steam_id"] == args.player]
        if not players:
            sys.exit(f"未找到玩家: {args.player}")

    print(f"📡 开始采集 {len(players)} 位玩家 × {page_count} 页数据\n")

    ok_count = 0
    fail_count = 0

    for player in players:
        steam_id = player["steam_id"]
        alias = player["alias"]

        for pg in range(1, page_count + 1):
            suffix = f"_{pg}" if pg > 1 else ""
            out_path = data_dir / f"{steam_id}_raw{suffix}.txt"

            try:
                text = fetch_player_page(steam_id, pg)
                if not text:
                    print(f"⏭️  {alias:4s}  page{pg} → 页面为空（可能无更多数据）")
                    continue

                out_path.write_text(text, encoding="utf-8")

                # 验证：检查是否包含 match 数据
                match_count = len(re.findall(r"^\*\*Squad", text, re.MULTILINE))
                print(f"✅ {alias:4s}  page{pg} → {len(text):5d} chars  {match_count} matches  {out_path.name}")
                ok_count += 1

            except requests.HTTPError as e:
                print(f"❌ {alias:4s}  page{pg} → HTTP {e.response.status_code}")
                fail_count += 1
            except Exception as e:
                print(f"❌ {alias:4s}  page{pg} → {e}")
                fail_count += 1

            time.sleep(1.2)  # 礼貌限速

    print(f"\n{'='*50}")
    print(f"  采集完成: ✅ {ok_count} 页  ❌ {fail_count} 页")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
