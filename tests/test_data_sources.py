from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.config import load_config
from src.data_sources import load_raw_snapshot


class DataSourceTests(unittest.TestCase):
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
