#!/usr/bin/env python3
"""生成 PUBG 每日战报的命令行入口。"""

from src import (
    compute_stats,
    compute_team_stats,
    generate_html_report,
    generate_report_screenshot,
    generate_titles_and_comments,
    get_time_range,
    parse_dakgg_markdown,
    regenerate_screenshot,
    run,
)
from src.cli import main
from src.parser import parse_time_label


def parse_time_ago(text, reference_time):
    """兼容旧接口，仅返回解析后的 datetime。"""
    return parse_time_label(text, reference_time)[0]

__all__ = [
    "compute_stats",
    "compute_team_stats",
    "generate_html_report",
    "generate_report_screenshot",
    "generate_titles_and_comments",
    "get_time_range",
    "parse_dakgg_markdown",
    "parse_time_ago",
    "regenerate_screenshot",
    "run",
]


if __name__ == "__main__":
    main()
