"""使用 Chrome/Chromium 将独立 HTML 报告渲染为 PNG。"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


def _find_chrome() -> str:
    local_app_data = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("PROGRAMFILES")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)")

    candidates = [
        # Windows：Chrome 和 Edge 通常不会自动加入 PATH。
        Path(local_app_data) / "Google/Chrome/Application/chrome.exe"
        if local_app_data
        else None,
        Path(local_app_data) / "Microsoft/Edge/Application/msedge.exe"
        if local_app_data
        else None,
        Path(program_files) / "Google/Chrome/Application/chrome.exe"
        if program_files
        else None,
        Path(program_files) / "Microsoft/Edge/Application/msedge.exe"
        if program_files
        else None,
        Path(program_files_x86) / "Google/Chrome/Application/chrome.exe"
        if program_files_x86
        else None,
        Path(program_files_x86) / "Microsoft/Edge/Application/msedge.exe"
        if program_files_x86
        else None,
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("chrome"),
        shutil.which("msedge"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise FileNotFoundError(
        "未找到 Google Chrome、Microsoft Edge 或 Chromium，无法生成 PNG 截图"
    )


def generate_report_screenshot(
    html_path: str | Path,
    png_path: str | Path,
    max_height: int = 6000,
) -> Path:
    try:
        from PIL import Image, ImageChops
    except ImportError as exc:
        raise RuntimeError("生成截图需要 Pillow：pip install Pillow") from exc

    html_path = Path(html_path).resolve()
    png_path = Path(png_path).resolve()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    chrome = _find_chrome()
    width = 760

    with tempfile.TemporaryDirectory(prefix="pubg_capture_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        raw_path = temp_dir / "raw.png"
        profile_path = temp_dir / "chrome_profile"
        command = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-sync",
            "--hide-scrollbars",
            "--no-default-browser-check",
            "--no-first-run",
            "--no-sandbox",
            "--force-device-scale-factor=1",
            f"--user-data-dir={profile_path}",
            f"--window-size={width + 28},{max_height}",
            f"--screenshot={raw_path}",
            f"{html_path.as_uri()}?capture=1",
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        screenshot_ready = False
        last_size = -1
        stable_checks = 0
        deadline = time.monotonic() + 30
        try:
            while time.monotonic() < deadline:
                if raw_path.exists():
                    current_size = raw_path.stat().st_size
                    if current_size > 0 and current_size == last_size:
                        stable_checks += 1
                        if stable_checks >= 2:
                            screenshot_ready = True
                            break
                    else:
                        stable_checks = 0
                        last_size = current_size
                if process.poll() is not None and not raw_path.exists():
                    break
                time.sleep(0.2)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

        if not screenshot_ready:
            raise RuntimeError("Chrome 截图超时或未生成图片")

        with Image.open(raw_path) as image:
            image = image.convert("RGB")
            black = Image.new("RGB", image.size, (0, 0, 0))
            content_box = ImageChops.difference(image, black).getbbox()
            if not content_box:
                raise RuntimeError("Chrome 截图为空白")
            content_bottom = min(content_box[3] + 1, image.height)
            if content_bottom >= image.height - 2:
                raise RuntimeError(f"页面高度超过截图上限 {max_height}px")
            cropped = image.crop((content_box[0], 0, content_box[2], content_bottom))
            if cropped.width != width:
                raise RuntimeError(
                    f"截图宽度异常：期望 {width}px，实际 {cropped.width}px"
                )
            cropped.save(png_path, optimize=True)
    return png_path


def regenerate_screenshot(html_path: str | Path, png_path: str | Path) -> Path:
    return generate_report_screenshot(html_path, png_path)
