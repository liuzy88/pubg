from __future__ import annotations

import unittest
from datetime import datetime

from fetch_matches import (
    FetchedPage,
    matches_json_to_markdown,
    page_covers_target_start,
)
from src.parser import parse_dakgg_markdown


class FetchDataTests(unittest.TestCase):
    def test_page_stops_when_oldest_match_covers_target_start(self) -> None:
        target = datetime.fromisoformat("2026-07-15T06:00:00+08:00")
        page = FetchedPage(
            text="data",
            match_count=10,
            newest_at=datetime.fromisoformat("2026-07-15T10:00:00+08:00"),
            oldest_at=datetime.fromisoformat("2026-07-15T05:30:00+08:00"),
            has_more=True,
        )
        self.assertTrue(page_covers_target_start(page, target))

    def test_page_continues_when_all_matches_are_too_new(self) -> None:
        target = datetime.fromisoformat("2026-07-15T06:00:00+08:00")
        page = FetchedPage(
            text="data",
            match_count=10,
            newest_at=datetime.fromisoformat("2026-07-15T18:00:00+08:00"),
            oldest_at=datetime.fromisoformat("2026-07-15T07:00:00+08:00"),
            has_more=True,
        )
        self.assertFalse(page_covers_target_start(page, target))

    def test_api_match_is_converted_to_parser_format(self) -> None:
        matches = [
            {
                "id": "match-123",
                "createdAt": "2026-07-15T16:00:09.000Z",
                "gameMode": "squad",
                "mapName": "Summerland_Main",
                "isCustomMatch": False,
                "participants": [
                    {
                        "teamRank": 7,
                        "teamTotal": 16,
                        "dbnos": 1,
                        "damageDealt": 231.4,
                        "kills": 2,
                        "name": "Alpha",
                        "playerId": "account.alpha",
                        "walkDistance": 2000,
                        "rideDistance": 500,
                        "swimDistance": 0,
                        "timeSurvived": 779,
                        "longestKill": 43.8,
                        "mainWeapon": "WeapHK416_C",
                    },
                    {
                        "name": "Bravo",
                        "playerId": "account.bravo",
                    },
                ],
            }
        ]
        text = matches_json_to_markdown(matches, "Alpha", "account.alpha")
        self.assertIn("Match ID match-123", text)
        self.assertIn("**Squad _(Normal)_**", text)
        self.assertIn("Map Karakin", text)
        self.assertIn("Weapon M416", text)
        self.assertIn("2026-07-15T16:00:09.000Z", text)

        parsed = parse_dakgg_markdown(
            text,
            "Alpha",
            datetime.fromisoformat("2026-07-16T08:30:00+08:00"),
            datetime.fromisoformat("2026-07-15T06:00:00+08:00"),
            datetime.fromisoformat("2026-07-16T05:59:59.999999+08:00"),
        )
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["match_key"], "dakgg:match-123")
        self.assertEqual(parsed[0]["damage"], 231)
        self.assertEqual(parsed[0]["teammates"], ["Alpha", "Bravo"])


if __name__ == "__main__":
    unittest.main()
