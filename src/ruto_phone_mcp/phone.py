import json
import logging
import os
import platform
import re
import subprocess
import time
from pathlib import Path
from io import BytesIO
from typing import Optional

from langchain.tools import tool
from PIL import Image, UnidentifiedImageError

from ruto_phone_mcp.config_utils import resolve_default_config_file


class RutoPhone:
    def __init__(self, adb: str | None = None, device_id: Optional[str] = None):
        phone_config = self._load_default_phone_config()
        self.is_android = self._is_android_runtime()
        self._adb = str(adb if adb is not None else phone_config.get("adb", "adb"))
        configured_device_id = phone_config.get("device_id")
        self._device_id = device_id if device_id is not None else (str(configured_device_id) if configured_device_id else None)
        self._local_rutophone_dex = os.path.join(os.path.dirname(__file__), "rutophone.dex")
        self._remote_rutophone_dex = "/data/local/tmp/rutophone.dex"
        self._screenshot_tmp_path = "/data/local/tmp/rutophone-screenshot.png"
        self._double_click_interval = 0.1
        self._long_click_duration_ms = 800
        self._swipe_duration_ms = 800
        self.logger = logging.getLogger(f"{__name__}.RutoPhone")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s"))
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        if self.is_android:
            self._command_prefix: list[str] = []
        else:
            self._command_prefix = [self._adb]
            if self._device_id:
                self._command_prefix.extend(["-s", self._device_id])

        return_format = (
            "The tool always returns plain text starting with 'OK:' on success or 'ERROR:' on failure. "
            "Use that prefix to judge whether the action succeeded."
        )
        self.tools = [
            tool("launch", description=(
                "Launch an Android application by package name. "
                "The package_name input must be the full Android package identifier, such as com.android.settings "
                "or com.example.app. Use this when you need to open an app before interacting with its UI. "
                f"{return_format}"
            ))(self.launch),
            tool("current_app", description=(
                "Get the package name of the application currently shown in the foreground. "
                "Use this to confirm which app is currently active before or after navigation. "
                f"{return_format}"
            ))(self.current_app),
            tool("list_apps", description=(
                "List installed Android apps by invoking the bundled rutophone.dex helper through app_process. "
                "Return lines are expected in the format 'package_name: app_name', for example 'com.tencent.mobileqq: QQ'. "
                "By default, only third-party apps are returned. Set third_party_only to false only when you explicitly need system apps too. "
                f"{return_format}"
            ))(self.list_apps),
            tool("click", description=(
                "Tap once on the screen using relative screen coordinates. "
                "Coordinates are percentages of the visible screen, not pixels. "
                "Top-left is (0, 0), bottom-right is (100, 100), and center is (50, 50). "
                "All coordinates must be integers from 0 to 100 inclusive. "
                "Always choose the visual center of the control you want to touch. "
                f"{return_format}"
            ))(self.click),
            tool("double_click", description=(
                "Double tap on the screen using the same coordinate system as click. "
                "Always choose the visual center of the target control. "
                f"{return_format}"
            ))(self.double_click),
            tool("long_click", description=(
                "Long press on the screen using the same coordinate system as click. "
                "Always choose the visual center of the target control. "
                f"{return_format}"
            ))(self.long_click),
            tool("swipe", description=(
                "Swipe using the same coordinate system as click. "
                "x1,y1 is the start point and x2,y2 is the end point. "
                "Choose visually centered start and end points. "
                f"{return_format}"
            ))(self.swipe),
            tool("back", description=(
                "Press the Android back button. Use this to close the current page, dismiss a dialog, "
                "leave a detail screen, or move back in the app navigation stack. "
                f"{return_format}"
            ))(self.back),
            tool("home", description=(
                "Press the Android home button. Use this to leave the current app and return to the device home screen. "
                f"{return_format}"
            ))(self.home),
        ]

    @staticmethod
    def _load_default_phone_config() -> dict:
        config_path = resolve_default_config_file(__file__, "phone.json")
        if not config_path.exists():
            return {}
        with config_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _is_android_runtime() -> bool:
        if "android" in platform.platform().lower():
            return True
        android_env_vars = ("ANDROID_ROOT", "ANDROID_DATA", "TERMUX_VERSION")
        return any(os.getenv(name) for name in android_env_vars)

    def _run(self, *args: str, capture_output: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            [*self._command_prefix, *args],
            check=True,
            capture_output=capture_output,
        )

    def _run_shell(self, *args: str, capture_output: bool = True) -> subprocess.CompletedProcess:
        if self.is_android:
            return self._run(*args, capture_output=capture_output)
        return self._run("shell", *args, capture_output=capture_output)

    def _log_result(self, action: str, params: dict, result: str) -> str:
        message = f"action={action} params={params} result={result}"
        if result.startswith("ERROR:"):
            self.logger.error(message)
        else:
            self.logger.info(message)
        return result

    def _ok_message(self, message: str) -> str:
        return f"OK: {message}"

    def _error_message(self, action: str, error: Exception | str) -> str:
        if isinstance(error, subprocess.CalledProcessError):
            stdout = (error.stdout or b"").decode("utf-8", errors="ignore").strip()
            stderr = (error.stderr or b"").decode("utf-8", errors="ignore").strip()
            details = stderr or stdout or f"command failed with exit code {error.returncode}"
            return f"ERROR: Failed to {action}: {details}."
        return f"ERROR: Failed to {action}: {error}."

    @staticmethod
    def _validate_percent(value: int, name: str) -> int:
        value = int(value)
        while value > 100:
            value = value / 10
        if value < 0 or value > 100:
            raise ValueError(f"{name} must be an integer from 0 to 100 inclusive")
        return value

    def _to_absolute_point(self, x: int, y: int) -> tuple[int, int]:
        x = self._validate_percent(x, "x")
        y = self._validate_percent(y, "y")
        width, height = self.size()
        px = round((width - 1) * x / 100)
        py = round((height - 1) * y / 100)
        return px, py

    def _to_absolute_swipe(self, x1: int, y1: int, x2: int, y2: int) -> tuple[int, int, int, int]:
        x1 = self._validate_percent(x1, "x1")
        y1 = self._validate_percent(y1, "y1")
        x2 = self._validate_percent(x2, "x2")
        y2 = self._validate_percent(y2, "y2")
        width, height = self.size()
        return (
            round((width - 1) * x1 / 100),
            round((height - 1) * y1 / 100),
            round((width - 1) * x2 / 100),
            round((height - 1) * y2 / 100),
        )

    def _click_pixels(self, x: int, y: int) -> None:
        self._run_shell("input", "tap", str(x), str(y), capture_output=False)

    def _swipe_pixels(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> None:
        self._run_shell(
            "input",
            "swipe",
            str(x1),
            str(y1),
            str(x2),
            str(y2),
            str(duration_ms),
            capture_output=False,
        )

    def _ensure_rutophone_dex(self) -> str:
        if not os.path.exists(self._local_rutophone_dex):
            raise FileNotFoundError(f"rutophone.dex not found at {self._local_rutophone_dex}")

        if self.is_android:
            return self._local_rutophone_dex

        self._run("push", self._local_rutophone_dex, self._remote_rutophone_dex)
        return self._remote_rutophone_dex

    def _run_rutophone_dex(self, *args: str) -> subprocess.CompletedProcess:
        dex_path = self._ensure_rutophone_dex()
        if self.is_android:
            return self._run(
                "/system/bin/app_process",
                f"-Djava.class.path={dex_path}",
                "/system/bin",
                "dex.rutophone.Main",
                *args,
            )
        return self._run(
            "shell",
            "/system/bin/app_process",
            f"-Djava.class.path={dex_path}",
            "/system/bin",
            "dex.rutophone.Main",
            *args,
        )

    @staticmethod
    def _extract_package_name(text: str) -> Optional[str]:
        patterns = [
            r"mCurrentFocus=Window\{[^}]+\s([A-Za-z0-9._]+)/(?:[A-Za-z0-9._$]+|\.)",
            r"mFocusedApp=.*? ([A-Za-z0-9._]+)/",
            r"topResumedActivity.*? ([A-Za-z0-9._]+)/",
            r"mResumedActivity:.*? ([A-Za-z0-9._]+)/",
            r"ResumedActivity:.*? ([A-Za-z0-9._]+)/",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def launch(self, package_name: str) -> str:
        package_name = package_name.strip()
        if not package_name:
            return self._log_result(
                "launch",
                {"package_name": package_name},
                self._error_message("launch app", "package_name must not be empty"),
            )
        try:
            self._run_shell(
                "monkey",
                "-p",
                package_name,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            )
            result = self._ok_message(f"Launched app {package_name}.")
        except Exception as error:
            result = self._error_message(f"launch app {package_name}", error)
        return self._log_result("launch", {"package_name": package_name}, result)

    def current_app(self) -> str:
        try:
            commands = [
                ("dumpsys", "window", "windows"),
                ("dumpsys", "window"),
                ("dumpsys", "activity", "activities"),
            ]
            result = self._error_message(
                "get current app",
                "unable to determine the current foreground app package",
            )
            for command in commands:
                command_result = self._run_shell(*command)
                package_name = self._extract_package_name(
                    command_result.stdout.decode("utf-8", errors="ignore")
                )
                if package_name:
                    result = self._ok_message(f"Current foreground app is {package_name}.")
                    break
        except Exception as error:
            result = self._error_message("get current app", error)
        return self._log_result("current_app", {}, result)

    def list_apps(self, third_party_only: bool = True) -> str:
        try:
            command = ["list-apps"]
            if not third_party_only:
                command.append("--include-system")
            run_result = self._run_rutophone_dex(*command)
            output = run_result.stdout.decode("utf-8", errors="ignore").strip()
            if not output:
                if third_party_only:
                    result = self._ok_message("Found 0 installed third-party apps.")
                else:
                    result = self._ok_message("Found 0 installed apps.")
            elif third_party_only:
                result = self._ok_message(
                    "Listed installed third-party apps from rutophone.dex in the format "
                    f"'package_name: app_name': {output}"
                )
            else:
                result = self._ok_message(
                    "Listed installed apps from rutophone.dex in the format "
                    f"'package_name: app_name': {output}"
                )
        except Exception as error:
            result = self._error_message("list installed apps", error)
        return self._log_result("list_apps", {"third_party_only": third_party_only}, result)

    def click(self, x: int, y: int) -> str:
        try:
            px, py = self._to_absolute_point(x, y)
            self._click_pixels(px, py)
            result = self._ok_message(f"Tapped the screen at {int(x)}% x, {int(y)}% y.")
        except Exception as error:
            result = self._error_message(f"tap the screen at {x}% x, {y}% y", error)
        return self._log_result("click", {"x": x, "y": y}, result)

    def double_click(self, x: int, y: int) -> str:
        try:
            px, py = self._to_absolute_point(x, y)
            self._click_pixels(px, py)
            time.sleep(self._double_click_interval)
            self._click_pixels(px, py)
            result = self._ok_message(f"Double tapped the screen at {int(x)}% x, {int(y)}% y.")
        except Exception as error:
            result = self._error_message(f"double tap the screen at {x}% x, {y}% y", error)
        return self._log_result("double_click", {"x": x, "y": y}, result)

    def long_click(self, x: int, y: int) -> str:
        try:
            px, py = self._to_absolute_point(x, y)
            self._swipe_pixels(px, py, px, py, duration_ms=self._long_click_duration_ms)
            result = self._ok_message(f"Long pressed the screen at {int(x)}% x, {int(y)}% y.")
        except Exception as error:
            result = self._error_message(f"long press the screen at {x}% x, {y}% y", error)
        return self._log_result("long_click", {"x": x, "y": y}, result)

    def swipe(self, x1: int, y1: int, x2: int, y2: int) -> str:
        try:
            start_x, start_y, end_x, end_y = self._to_absolute_swipe(x1, y1, x2, y2)
            self._swipe_pixels(start_x, start_y, end_x, end_y, duration_ms=self._swipe_duration_ms)
            result = self._ok_message(f"Swiped from {int(x1)}% x, {int(y1)}% y to {int(x2)}% x, {int(y2)}% y.")
        except Exception as error:
            result = self._error_message(
                f"swipe from {x1}% x, {y1}% y to {x2}% x, {y2}% y",
                error,
            )
        return self._log_result("swipe", {"x1": x1, "y1": y1, "x2": x2, "y2": y2}, result)

    def back(self) -> str:
        try:
            self._run_shell("input", "keyevent", "4", capture_output=False)
            result = self._ok_message("Pressed the Android back button.")
        except Exception as error:
            result = self._error_message("press the Android back button", error)
        return self._log_result("back", {}, result)

    def home(self) -> str:
        try:
            self._run_shell("input", "keyevent", "3", capture_output=False)
            result = self._ok_message("Pressed the Android home button.")
        except Exception as error:
            result = self._error_message("press the Android home button", error)
        return self._log_result("home", {}, result)

    def screenshot(self) -> bytes:
        self._run_shell("rm", "-f", self._screenshot_tmp_path, capture_output=False)
        self._run_shell("screencap", "-p", self._screenshot_tmp_path)

        if self.is_android:
            with open(self._screenshot_tmp_path, "rb") as file:
                png_data = file.read()
            self._run_shell("rm", "-f", self._screenshot_tmp_path, capture_output=False)
        else:
            result = self._run_shell("cat", self._screenshot_tmp_path)
            png_data = result.stdout
            self._run_shell("rm", "-f", self._screenshot_tmp_path, capture_output=False)

        png_data = png_data.replace(b"\r\n", b"\n")
        if not png_data.startswith(b"\x89PNG\n\x1a\n") and not png_data.startswith(b"\x89PNG\r\n\x1a\n"):
            preview = png_data[:120].decode("utf-8", errors="ignore").strip()
            if not preview:
                preview = repr(png_data[:32])
            raise ValueError(f"Screenshot command returned non-PNG data. Preview: {preview}")
        return png_data

    def screenshot_webp(self, quality: int = 0) -> bytes:
        png_data = self.screenshot()
        try:
            with Image.open(BytesIO(png_data)) as image:
                image.load()
                output = BytesIO()
                image.save(output, format="WEBP", quality=max(0, min(100, int(quality))))
            return output.getvalue()
        except UnidentifiedImageError as error:
            raise ValueError("Failed to convert screenshot to WebP because the screenshot data is not a valid image.") from error

    def size(self) -> tuple[int, int]:
        result = self._run_shell("wm", "size")
        match = re.search(r"(\d+)x(\d+)", result.stdout.decode("utf-8", errors="ignore"))
        if not match:
            raise ValueError("Unable to parse screen size output.")
        return int(match.group(1)), int(match.group(2))
