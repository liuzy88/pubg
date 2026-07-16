from __future__ import annotations

import unittest
from datetime import datetime

from src.parser import parse_dakgg_markdown, parse_time_label


SCRAPED_AT = datetime.fromisoformat("2026-07-16T08:30:00+08:00")
START = datetime.fromisoformat("2026-07-15T06:00:00+08:00")
END = datetime.fromisoformat("2026-07-16T05:59:59.999999+08:00")


class ParserTests(unittest.TestCase):
    def test_relative_time_uses_fixed_scrape_time(self) -> None:
        parsed, precision = parse_time_label("12h ago", SCRAPED_AT)
        self.assertEqual(
            parsed,
            datetime.fromisoformat("2026-07-15T20:30:00+08:00"),
        )
        self.assertEqual(precision, "hour")

    def test_missing_time_is_not_silently_included(self) -> None:
        text = """
#### Match
**Squad _(Normal)_**
#1/18
Map Karakin
Kills 2
Damage 200
"""
        self.assertEqual(
            parse_dakgg_markdown(text, "测试", SCRAPED_AT, START, END),
            [],
        )

    def test_parser_supports_mode_without_type_and_assigns_match_key(self) -> None:
        text = """
#### Match
**Squad**
#2/18
12h ago
Map
Rondo
Weapon
M416
Kills
2
Damage
231
- [Alpha](https://example.test/Alpha)
- [Bravo](https://example.test/Bravo)
"""
        matches = parse_dakgg_markdown(
            text,
            "Alpha",
            SCRAPED_AT,
            START,
            END,
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["type"], "Unknown")
        self.assertEqual(matches[0]["map"], "Rondo")
        self.assertEqual(matches[0]["kills"], 2)
        self.assertTrue(matches[0]["match_key"])

    def test_fixed_date_is_stable(self) -> None:
        parsed, precision = parse_time_label("15 Jul", SCRAPED_AT)
        self.assertEqual(
            parsed,
            datetime.fromisoformat("2026-07-15T12:00:00+08:00"),
        )
        self.assertEqual(precision, "date")

    def test_iso_time_is_preferred_when_available(self) -> None:
        parsed, precision = parse_time_label(
            "2026-07-15T22:10:00Z",
            SCRAPED_AT,
        )
        self.assertEqual(
            parsed,
            datetime.fromisoformat("2026-07-16T06:10:00+08:00"),
        )
        self.assertEqual(precision, "exact")


if __name__ == "__main__":
    unittest.main()
