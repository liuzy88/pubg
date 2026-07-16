from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.screenshot import _find_chrome


class ScreenshotBrowserDiscoveryTests(unittest.TestCase):
    def test_finds_edge_in_windows_program_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            edge = Path(temp_dir) / "Microsoft/Edge/Application/msedge.exe"
            edge.parent.mkdir(parents=True)
            edge.touch()

            environment = {
                "PROGRAMFILES": temp_dir,
                "LOCALAPPDATA": "",
                "PROGRAMFILES(X86)": "",
            }
            with (
                patch.dict(os.environ, environment, clear=False),
                patch("src.screenshot.shutil.which", return_value=None),
            ):
                self.assertEqual(_find_chrome(), str(edge))

    def test_finds_browser_from_path(self) -> None:
        executable = Path(__file__).resolve()
        with (
            patch.dict(
                os.environ,
                {
                    "PROGRAMFILES": "",
                    "LOCALAPPDATA": "",
                    "PROGRAMFILES(X86)": "",
                },
                clear=False,
            ),
            patch(
                "src.screenshot.shutil.which",
                side_effect=lambda name: str(executable) if name == "msedge" else None,
            ),
        ):
            self.assertEqual(_find_chrome(), str(executable))


if __name__ == "__main__":
    unittest.main()
