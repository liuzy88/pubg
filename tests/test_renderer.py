from __future__ import annotations

import unittest
from datetime import datetime

from src.renderer import generate_html_report


class RendererTests(unittest.TestCase):
    def test_external_text_is_html_escaped(self) -> None:
        stats = {
            "evil": {
                "alias": "<script>alert(1)</script>",
                "steam_id": "evil",
                "match_count": 1,
                "total_kills": 1,
                "total_damage": 100,
                "total_dbnos": 0,
                "estimated_kd": 1,
                "kda": 1,
                "avg_kills": 1,
                "avg_damage": 100,
                "chicken_dinners": 0,
                "best_placement": 2,
                "map_stats": {"<b>map</b>": 1},
            }
        }
        html = generate_html_report(
            stats,
            {
                "unique_match_count": 1,
                "unique_chicken_count": 0,
                "combos": [],
            },
            [
                {
                    "title": "<title>",
                    "player": "<player>",
                    "value": "<value>",
                    "comment": "<comment>",
                }
            ],
            ["<img src=x onerror=alert(1)>"],
            datetime(2026, 7, 15, 6),
            datetime(2026, 7, 16, 5, 59),
            datetime(2026, 7, 16, 8, 30),
        )
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("实际比赛", html)
        self.assertIn("估算KD", html)


if __name__ == "__main__":
    unittest.main()
