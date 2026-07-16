from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.config import load_config
from src.data_sources import load_raw_snapshot


class DataSourceTests(unittest.TestCase):
    def test_manifest_loads_shared_matches_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "matches.csv").write_text("created_at,match_id,steam_id\n")
            (root / "conf.json").write_text(
                json.dumps(
                    {
                        "players": [
                            {"alias": "P1", "steam_id": "p1"},
                            {"alias": "P2", "steam_id": "p2"},
                        ],
                        "dakgg": {
                            "api_base_url": "https://example/api/v1",
                            "max_pages": 30,
                            "keep_modes": ["Squad"],
                        },
                        "output": {
                            "data_dir": "data",
                            "report_dir": "reports",
                        },
                    }
                )
            )
            (data_dir / "fetch_manifest.json").write_text(
                json.dumps(
                    {
                        "scraped_at": "2026-07-16T08:30:00+08:00",
                        "matches_file": "matches.csv",
                        "format": "player-match-csv",
                        "players": {},
                    }
                )
            )
            snapshot = load_raw_snapshot(load_config(root / "conf.json"))
            self.assertEqual(snapshot.player_pages["p1"][0].path.name, "matches.csv")
            self.assertEqual(
                snapshot.player_pages["p2"][0].format,
                "player-match-csv",
            )

    def test_manifest_loads_single_api_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "p_matches.json").write_text('{"matches": []}')
            (root / "conf.json").write_text(
                json.dumps(
                    {
                        "players": [{"alias": "P", "steam_id": "p"}],
                        "dakgg": {
                            "api_base_url": "https://example/api/v1",
                            "max_pages": 30,
                            "keep_modes": ["Squad"],
                        },
                        "output": {
                            "data_dir": "data",
                            "report_dir": "reports",
                        },
                    }
                )
            )
            (data_dir / "fetch_manifest.json").write_text(
                json.dumps(
                    {
                        "scraped_at": "2026-07-16T08:30:00+08:00",
                        "players": {
                            "p": {
                                "file": "p_matches.json",
                                "format": "dakgg-api-json",
                            }
                        },
                    }
                )
            )
            snapshot = load_raw_snapshot(load_config(root / "conf.json"))
            source = snapshot.player_pages["p"][0]
            self.assertEqual(source.path.name, "p_matches.json")
            self.assertEqual(source.format, "dakgg-api-json")

    def test_manifest_excludes_stale_raw_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "p_raw.txt").write_text("page1")
            (data_dir / "p_raw_2.txt").write_text("stale")
            (root / "conf.json").write_text(
                json.dumps(
                    {
                        "players": [{"alias": "P", "steam_id": "p"}],
                        "dakgg": {
                            "api_base_url": "https://example/api/v1",
                            "page_count": 2,
                            "keep_modes": ["Squad"],
                        },
                        "output": {
                            "data_dir": "data",
                            "report_dir": "reports",
                        },
                    }
                )
            )
            (data_dir / "fetch_manifest.json").write_text(
                json.dumps(
                    {
                        "scraped_at": "2026-07-16T08:30:00+08:00",
                        "players": {
                            "p": {
                                "pages": [
                                    {
                                        "page": 1,
                                        "file": "p_raw.txt",
                                        "scraped_at": "2026-07-16T08:30:00+08:00",
                                    }
                                ]
                            }
                        },
                    }
                )
            )
            snapshot = load_raw_snapshot(load_config(root / "conf.json"))
            self.assertEqual(
                [page.path.name for page in snapshot.player_pages["p"]],
                ["p_raw.txt"],
            )


if __name__ == "__main__":
    unittest.main()
