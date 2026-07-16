#!/usr/bin/env python3
"""兼容入口：业务代码位于 pubg_report 包。"""

from pubg_report import (
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
from pubg_report.cli import main
from pubg_report.parser import parse_time_label


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
