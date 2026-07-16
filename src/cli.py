"""命令行入口。"""

from __future__ import annotations

import argparse

from .pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="PUBG 每日战报生成器")
    parser.add_argument("--days-ago", type=int, default=1, help="1=昨天，2=前天")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument(
        "--no-screenshot",
        action="store_true",
        help="只生成 HTML 和 JSON，不调用 Chrome",
    )
    args = parser.parse_args()
    report = run(
        days_ago=args.days_ago,
        config_path=args.config,
        generate_screenshot=not args.no_screenshot,
    )
    print(f"🎉 完成！战报路径: {report}")
