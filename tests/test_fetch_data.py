from __future__ import annotations

import unittest
import tempfile
from datetime import datetime
from pathlib import Path

from fetch_matches import (
    CSV_FIELDS,
    FetchedPage,
    _append_new_rows,
    page_covers_target_start,
)
from src.parser import parse_dakgg_api_matches


class FetchDataTests(unittest.TestCase):
    def test_csv_appends_only_new_player_match_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            existing = root / "matches.csv"
            row = {field: "" for field in CSV_FIELDS}
            row.update(
                {
                    "created_at": "2026-07-15T10:00:00+08:00",
                    "match_id": "m1",
                    "steam_id": "p1",
                }
            )
            self.assertEqual(_append_new_rows(existing, [row]), 1)
            second = dict(row)
            second["match_id"] = "m2"
            self.assertEqual(
                _append_new_rows(existing, [row, second]),
                1,
            )
            lines = existing.read_text().splitlines()
            self.assertEqual(len(lines), 3)
            before = existing.read_bytes()
            self.assertEqual(_append_new_rows(existing, [row, second]), 0)
            self.assertEqual(existing.read_bytes(), before)

    def test_page_stops_when_oldest_match_covers_target_start(self) -> None:
        target = datetime.fromisoformat("2026-07-15T06:00:00+08:00")
        page = FetchedPage(
            matches=[{"id": "one"}],
            match_count=10,
            newest_at=datetime.fromisoformat("2026-07-15T10:00:00+08:00"),
            oldest_at=datetime.fromisoformat("2026-07-15T05:30:00+08:00"),
            has_more=True,
        )
        self.assertTrue(page_covers_target_start(page, target))

    def test_page_continues_when_all_matches_are_too_new(self) -> None:
        target = datetime.fromisoformat("2026-07-15T06:00:00+08:00")
        page = FetchedPage(
            matches=[{"id": "one"}],
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
        parsed = parse_dakgg_api_matches(
            matches,
            "Alpha",
            "Alpha",
            datetime.fromisoformat("2026-07-15T06:00:00+08:00"),
            datetime.fromisoformat("2026-07-16T05:59:59.999999+08:00"),
        )
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["match_key"], "dakgg:match-123")
        self.assertEqual(parsed[0]["damage"], 231)
        self.assertEqual(parsed[0]["teammates"], ["Alpha", "Bravo"])
        self.assertEqual(parsed[0]["map"], "Karakin")
        self.assertEqual(parsed[0]["weapon"], "M416")


if __name__ == "__main__":
    unittest.main()
