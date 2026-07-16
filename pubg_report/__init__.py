"""PUBG 日报生成包。"""

from .awards import generate_titles_and_comments
from .config import AppConfig, get_time_range, load_config
from .parser import parse_dakgg_markdown, parse_time_label
from .pipeline import run
from .renderer import generate_html_report
from .screenshot import generate_report_screenshot, regenerate_screenshot
from .stats import compute_stats, compute_team_stats

__all__ = [
    "AppConfig",
    "compute_stats",
    "compute_team_stats",
    "generate_html_report",
    "generate_report_screenshot",
    "generate_titles_and_comments",
    "get_time_range",
    "load_config",
    "parse_dakgg_markdown",
    "parse_time_label",
    "regenerate_screenshot",
    "run",
]
