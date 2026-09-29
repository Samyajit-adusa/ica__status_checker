import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
from pathlib import Path

import customtkinter as ctk
import schedule
from playwright.sync_api import sync_playwright

DEFAULT_URL = "https://servicesessentials.ibm.com/curatorai/apps/ui/new-chat/"
APP_VERSION = "1.0.2"
GITHUB_REPOSITORY = "Samyajit-adusa/ica__status_checker"
GITHUB_RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
RELEASE_ASSET_NAME = "ica_automation.exe"
RELEASE_CHECKSUM_ASSET_NAME = f"{RELEASE_ASSET_NAME}.sha256"

def _default_profile_user_name():
    username = os.getenv("USERNAME") or os.getenv("USER") or "default-user"
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in username).strip()
    return safe_name or "default-user"


def _default_profile_dir():
    if os.getenv("LOCALAPPDATA"):
        base_dir = Path(os.environ["LOCALAPPDATA"]) / "IBM CuratorAI" / "browser_profiles"
    else:
        base_dir = Path.home() / ".ica_automation" / "browser_profiles"
    return base_dir / _default_profile_user_name()


DEFAULT_PROFILE_DIR = _default_profile_dir()
PAGE_TIMEOUT_SECONDS = 90
SELECTOR_TIMEOUT_SECONDS = 30
MAX_LOGIN_WAIT_SECONDS = 180
RESPONSE_TIMEOUT_SECONDS = 120
NETWORK_RETRY_ATTEMPTS = 3
NETWORK_RETRY_DELAY_SECONDS = 3
CHAT_TEXTAREA_SELECTOR = 'textarea#chat-input__text-area[data-testid="chat-input__textarea"]'
CHAT_TEXTAREA_FALLBACK_SELECTOR = 'textarea[placeholder="Ask a Question"]'
CHAT_SUBMIT_BUTTON_SELECTOR = 'button[type="submit"], button[data-testid*="send"], button[aria-label*="Send"], button[title*="Send"], button:has-text("Send")'


class BrowserAutomationApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("IBM CuratorAI Browser Runner")
        self.geometry("760x660")
        self.minsize(720, 600)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.default_profile_dir = _default_profile_dir()
        self.first_run = self._is_new_profile_path(self.default_profile_dir)
        self._ensure_profile_dir(self.default_profile_dir)
        self._ensure_packaged_inputs_file()

        self.url_var = ctk.StringVar(value=DEFAULT_URL)
        self.profile_var = ctk.StringVar(value=str(self.default_profile_dir))
        self.headless_var = ctk.BooleanVar(value=False)
        self.scheduler_var = ctk.BooleanVar(value=False)
        self.wait_for_response_var = ctk.BooleanVar(value=False)
        self.interval_var = ctk.StringVar(value="15")
        self.status_var = ctk.StringVar(value="Ready")

        self._run_lock = threading.Lock()
        self._scheduler_stop = threading.Event()
        self._scheduler_thread = None
        self._update_info = None
        self._update_check_in_progress = False

        self._build_ui()
        self.after(1500, self._check_for_updates)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        main_frame = ctk.CTkFrame(self, corner_radius=18)
        main_frame.grid(row=0, column=0, padx=18, pady=18, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            main_frame,
            text="Persistent Browser Automation",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title.grid(row=0, column=0, padx=18, pady=(18, 6), sticky="w")

        sub_title = ctk.CTkLabel(
            main_frame,
            text="Uses a reusable browser profile so your login credentials stay saved for future runs.",
            font=ctk.CTkFont(size=12),
            text_color="#b8d3ff",
        )
        sub_title.grid(row=1, column=0, padx=18, pady=(0, 12), sticky="w")

        form = ctk.CTkFrame(main_frame, corner_radius=14)
        form.grid(row=2, column=0, padx=18, pady=(0, 18), sticky="nsew")
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="URL").grid(row=0, column=0, padx=(18, 10), pady=(18, 8), sticky="w")
        ctk.CTkEntry(form, textvariable=self.url_var, placeholder_text="https://...").grid(
            row=0, column=1, padx=(0, 18), pady=(18, 8), sticky="ew"
        )

        ctk.CTkLabel(form, text="Profile folder").grid(row=1, column=0, padx=(18, 10), pady=8, sticky="w")
        ctk.CTkEntry(form, textvariable=self.profile_var).grid(
            row=1, column=1, padx=(0, 18), pady=8, sticky="ew"
        )

        options = ctk.CTkFrame(form, corner_radius=12)
        options.grid(row=2, column=0, columnspan=2, padx=18, pady=8, sticky="ew")
        options.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkSwitch(
            options,
            text="Headless mode",
            variable=self.headless_var,
            onvalue=True,
            offvalue=False,
        ).grid(row=0, column=0, padx=18, pady=12, sticky="w")

        ctk.CTkSwitch(
            options,
            text="Enable scheduler",
            variable=self.scheduler_var,
            onvalue=True,
            offvalue=False,
            command=self._toggle_scheduler,
        ).grid(row=0, column=1, padx=18, pady=12, sticky="e")

        ctk.CTkSwitch(
            options,
            text="Wait for response",
            variable=self.wait_for_response_var,
            onvalue=True,
            offvalue=False,
        ).grid(row=1, column=0, padx=18, pady=(0, 12), sticky="w")

        interval_frame = ctk.CTkFrame(form, corner_radius=10)
        interval_frame.grid(row=3, column=0, columnspan=2, padx=18, pady=(6, 18), sticky="ew")
        interval_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(interval_frame, text="Repeat every").grid(row=0, column=0, padx=(18, 10), pady=12, sticky="w")
        ctk.CTkEntry(interval_frame, textvariable=self.interval_var, width=120).grid(
            row=0, column=1, padx=(0, 8), pady=12, sticky="w"
        )
        ctk.CTkLabel(interval_frame, text="minutes").grid(row=0, column=2, padx=(0, 18), pady=12, sticky="w")

        button_row = ctk.CTkFrame(main_frame, corner_radius=12)
        button_row.grid(row=3, column=0, padx=18, pady=(0, 10), sticky="ew")
        button_row.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self.run_now_btn = ctk.CTkButton(button_row, text="Run now", command=self._start_background_run)
        self.run_now_btn.grid(row=0, column=0, padx=10, pady=12, sticky="ew")

        self.stop_btn = ctk.CTkButton(button_row, text="Stop scheduler", command=self._stop_scheduler, fg_color="#732d2d")
        self.stop_btn.grid(row=0, column=1, padx=10, pady=12, sticky="ew")

        self.check_session_btn = ctk.CTkButton(button_row, text="Check session", command=self._check_session_status)
        self.check_session_btn.grid(row=0, column=2, padx=10, pady=12, sticky="ew")

        self.clear_log_btn = ctk.CTkButton(button_row, text="Clear log", command=self._clear_log)
        self.clear_log_btn.grid(row=0, column=3, padx=10, pady=12, sticky="ew")

        self.update_btn = ctk.CTkButton(button_row, text="Check updates", command=self._check_for_updates)
        self.update_btn.grid(row=0, column=4, padx=10, pady=12, sticky="ew")

        self.log_box = ctk.CTkTextbox(main_frame, height=220, wrap="word")
        self.log_box.grid(row=4, column=0, padx=18, pady=(0, 12), sticky="nsew")

        status = ctk.CTkLabel(main_frame, textvariable=self.status_var, anchor="w")
        status.grid(row=5, column=0, padx=18, pady=(0, 18), sticky="ew")

        if self.first_run:
            self._append_log("First run detected: a new browser profile will be created for this device/account.")
            self._append_log("Complete the IBM sign-in once in the visible browser window so the saved session can be reused later.")
            self.after(250, self._show_first_run_setup_dialog)
        else:
            self._append_log("Existing browser profile found. The saved IBM session will be reused if it is still valid.")
        self._toggle_scheduler()

    def _append_log(self, message):
        def _write():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"{time.strftime('%H:%M:%S')} - {message}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

        self.after(0, _write)

    @staticmethod
    def _is_new_profile_path(profile_dir):
        profile_dir = Path(profile_dir).expanduser()
        if not profile_dir.exists():
            return True
        if not any(profile_dir.iterdir()):
            return True

        required_entries = {"Default", "Local State", "Preferences"}
        return not required_entries.intersection({item.name for item in profile_dir.iterdir()})

    def _ensure_profile_dir(self, profile_dir):
        profile_dir = Path(profile_dir).expanduser()
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "Default").mkdir(exist_ok=True)
        return profile_dir

    def _ensure_packaged_inputs_file(self):
        project_root_inputs = Path(__file__).resolve().parent / "inputs.txt"
        runtime_inputs = Path.home() / "AppData" / "Local" / "IBM CuratorAI" / "inputs.txt"

        if project_root_inputs.exists():
            source_inputs = project_root_inputs
        elif runtime_inputs.exists():
            source_inputs = runtime_inputs
        else:
            source_inputs = None

        if source_inputs is not None:
            runtime_inputs.parent.mkdir(parents=True, exist_ok=True)
            if not runtime_inputs.exists() or runtime_inputs.stat().st_size == 0:
                shutil.copy2(source_inputs, runtime_inputs)
        return runtime_inputs

    def _show_first_run_setup_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("First run setup")
        dialog.geometry("550x240")
        dialog.minsize(480, 200)
        dialog.transient(self)
        dialog.grab_set()

        label = ctk.CTkLabel(
            dialog,
            text=(
                "This is the first run for this device/account.\n\n"
                "A dedicated browser profile will be created for your IBM login.\n"
                "Please sign in once in the next browser window so the app can reuse it on future runs."
            ),
            justify="center",
            wraplength=500,
            font=ctk.CTkFont(size=14),
        )
        label.pack(padx=18, pady=(24, 12))

        button = ctk.CTkButton(dialog, text="Continue", command=lambda: (dialog.destroy(), self._start_background_run()))
        button.pack(pady=(0, 18))
        dialog.focus_set()

    def _show_login_required_dialog(self, message=None, on_continue=None):
        dialog = ctk.CTkToplevel(self)
        dialog.title("IBM login required")
        dialog.geometry("520x210")
        dialog.minsize(420, 180)
        dialog.transient(self)
        dialog.grab_set()

        body = message or (
            "IBM login has expired or was reset.\n"
            "The browser is switching to visible mode so you can sign in manually.\n"
            "After a successful login, the browser profile will save the session for future runs."
        )

        label = ctk.CTkLabel(
            dialog,
            text=body,
            justify="center",
            wraplength=480,
            font=ctk.CTkFont(size=14),
        )
        label.pack(padx=18, pady=(20, 10))

        def _close_and_continue():
            dialog.destroy()
            if on_continue is not None:
                on_continue()

        button = ctk.CTkButton(dialog, text="Continue", command=_close_and_continue)
        button.pack(pady=(0, 18))

        dialog.focus_set()

    def _open_manual_login_for_session_check(self):
        profile_dir = self._ensure_profile_dir(self.profile_var.get())
        self.status_var.set("Manual login in progress")
        self._append_log("Opening a visible browser so the IBM login can be completed manually.")

        browser = None
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=False,
                    viewport={"width": 1600, "height": 980},
                    args=["--disable-dev-shm-usage", "--window-size=1600,980", "--force-device-scale-factor=1"],
                )
                page = browser.new_page()
                if not self._load_page_with_retries(page, self.url_var.get(), "Opening manual IBM login"):
                    self.status_var.set("Manual login unavailable - network issue")
                    self._append_log("Could not open the IBM login page after retries. Please check your connection and try again.")
                    return

                deadline = time.time() + MAX_LOGIN_WAIT_SECONDS
                while time.time() < deadline:
                    if self._is_logged_in_success_page(page):
                        self._append_log("IBM chat window detected after manual login. Closing browser.")
                        self.status_var.set("Session refreshed")
                        time.sleep(1)
                        browser.close()
                        self.after(300, self._check_session_status)
                        return

                    if self._is_login_page(page):
                        self._append_log("IBM login screen is visible. Complete the sign-in and the app will close automatically when the chat page opens.")

                    page.wait_for_timeout(2000)

                self._append_log("Manual IBM login timed out. The browser remains open so you can finish signing in.")
                self.status_var.set("Manual login timed out")
        except Exception as exc:
            self.status_var.set("Manual login failed")
            self._append_log(f"Manual login flow failed: {exc}")
        finally:
            if browser is not None and browser.is_connected():
                browser.close()

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    @staticmethod
    def _version_tuple(version):
        return tuple(int(part) for part in version.lstrip("v").split("."))

    @staticmethod
    def _fetch_url(url):
        request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "ICA-Automation-Updater"})
        with urlopen(request, timeout=30) as response:
            return response.read()

    def _check_for_updates(self):
        if self._update_check_in_progress:
            return

        self._update_check_in_progress = True
        self.update_btn.configure(state="disabled", text="Checking...")

        def _run_check():
            try:
                release = json.loads(self._fetch_url(GITHUB_RELEASE_API_URL))
                latest_version = release["tag_name"].lstrip("v")
                if self._version_tuple(latest_version) <= self._version_tuple(APP_VERSION):
                    self.after(0, self._show_no_update_available)
                    return

                assets = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}
                if RELEASE_ASSET_NAME not in assets or RELEASE_CHECKSUM_ASSET_NAME not in assets:
                    raise RuntimeError("The latest release is missing its executable or SHA-256 checksum.")

                self._update_info = {
                    "version": latest_version,
                    "download_url": assets[RELEASE_ASSET_NAME],
                    "checksum_url": assets[RELEASE_CHECKSUM_ASSET_NAME],
                }
                self.after(0, self._show_update_available)
            except (KeyError, TypeError, ValueError, URLError, TimeoutError, OSError) as exc:
                self.after(0, lambda error=exc: self._show_update_check_failed(error))
            finally:
                self._update_check_in_progress = False

        threading.Thread(target=_run_check, daemon=True).start()

    def _show_no_update_available(self):
        self.update_btn.configure(state="normal", text="Check updates")
        self.status_var.set(f"Up to date (v{APP_VERSION})")
        self._append_log(f"No update available. Running v{APP_VERSION}.")

    def _show_update_available(self):
        version = self._update_info["version"]
        self.update_btn.configure(state="normal", text=f"Install v{version}", command=self._install_available_update)
        self.status_var.set(f"Update v{version} available")
        self._append_log(f"Update v{version} is available. Click Install v{version} to download and restart.")

    def _show_update_check_failed(self, exc):
        self.update_btn.configure(state="normal", text="Check updates")
        self._append_log(f"Update check could not be completed: {exc}")

    def _install_available_update(self):
        if self._update_info is None:
            return
        if not getattr(sys, "frozen", False):
            self.status_var.set("Build the app before installing updates")
            self._append_log("Updates can only replace the packaged executable, not app.py.")
            return

        self.update_btn.configure(state="disabled", text="Downloading...")
        self.status_var.set("Downloading update...")

        def _download_and_install():
            try:
                checksum_text = self._fetch_url(self._update_info["checksum_url"]).decode("ascii").strip()
                expected_checksum = checksum_text.split()[0].lower()
                if len(expected_checksum) != 64 or any(char not in "0123456789abcdef" for char in expected_checksum):
                    raise RuntimeError("The release checksum is invalid.")

                download_path = Path(tempfile.gettempdir()) / f"{RELEASE_ASSET_NAME}.{self._update_info['version']}.download"
                download_path.write_bytes(self._fetch_url(self._update_info["download_url"]))
                actual_checksum = hashlib.sha256(download_path.read_bytes()).hexdigest()
                if actual_checksum != expected_checksum:
                    download_path.unlink(missing_ok=True)
                    raise RuntimeError("Downloaded update failed SHA-256 verification.")

                self.after(0, lambda: self._replace_executable_and_restart(download_path))
            except (URLError, TimeoutError, OSError, RuntimeError) as exc:
                self.after(0, lambda error=exc: self._show_update_install_failed(error))

        threading.Thread(target=_download_and_install, daemon=True).start()

    def _replace_executable_and_restart(self, download_path):
        target_path = Path(sys.executable).resolve()
        script_path = Path(tempfile.gettempdir()) / "ica_automation_update.cmd"
        script_path.write_text(
            "@echo off\n"
            "timeout /t 2 /nobreak > nul\n"
            f'move /y "{download_path}" "{target_path}" > nul\n'
            f'start "" "{target_path}"\n'
            'del "%~f0"\n',
            encoding="ascii",
        )
        self._append_log("Update verified. Installing and restarting the application.")
        subprocess.Popen(["cmd.exe", "/c", str(script_path)], creationflags=subprocess.CREATE_NO_WINDOW)
        self.destroy()

    def _show_update_install_failed(self, exc):
        self.update_btn.configure(state="normal", text="Install failed")
        self.status_var.set("Update download failed")
        self._append_log(f"Update could not be installed: {exc}")

    @staticmethod
    def _is_transient_network_error(exc):
        message = str(exc).lower()
        transient_markers = (
            "timeout",
            "timed out",
            "net::",
            "connection",
            "network",
            "dns",
            "socket",
            "econn",
            "enotfound",
            "err_internet",
        )
        return any(marker in message for marker in transient_markers)

    def _load_page_with_retries(self, page, url=None, action="Loading IBM app"):
        for attempt in range(1, NETWORK_RETRY_ATTEMPTS + 1):
            try:
                if url is None:
                    page.reload(wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_SECONDS * 1000)
                else:
                    page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_SECONDS * 1000)
                return True
            except Exception as exc:
                if not self._is_transient_network_error(exc) or attempt == NETWORK_RETRY_ATTEMPTS:
                    self._append_log(f"{action} failed: {exc}")
                    return False

                delay = NETWORK_RETRY_DELAY_SECONDS * attempt
                self.status_var.set(f"Network issue - retrying ({attempt}/{NETWORK_RETRY_ATTEMPTS})")
                self._append_log(
                    f"{action} hit a temporary network issue (attempt {attempt}/{NETWORK_RETRY_ATTEMPTS}). "
                    f"Retrying in {delay} seconds: {exc}"
                )
                time.sleep(delay)

        return False

    def _is_logged_in_success_page(self, page):
        url = (page.url or "").lower()

        if "curatorai/apps/ui/new-chat" in url:
            for selector in [
                CHAT_TEXTAREA_SELECTOR,
                CHAT_TEXTAREA_FALLBACK_SELECTOR,
                "textarea[placeholder='Ask a Question']",
                "text=IBM Consulting Advantage",
                "text=History",
                "button:has-text('New Chat')",
            ]:
                try:
                    if page.locator(selector).first.is_visible(timeout=2000):
                        return True
                except Exception:
                    continue

        for locator_text in ["IBM Consulting Advantage", "History", "New Chat", "Chat"]:
            try:
                if page.locator(f"text={locator_text}").first.is_visible(timeout=2000):
                    return True
            except Exception:
                pass

        try:
            if page.locator("button:has-text('New Chat')").is_visible(timeout=2000):
                return True
        except Exception:
            pass

        try:
            if page.locator(CHAT_TEXTAREA_SELECTOR).is_visible(timeout=2000):
                return True
        except Exception:
            pass

        return False

    def _is_login_page(self, page):
        url = (page.url or "").lower()
        if self._is_logged_in_success_page(page):
            return False

        if "servicesessentials.ibm.com/curatorai/apps/ui/new-chat" in url:
            return False

        if any(token in url for token in ["login", "signin", "auth", "sps", "ibmid", "oauth", "callback"]):
            return True

        for locator_text in [
            "Log in to IBM",
            "IBMid",
            "Continue with Google",
            "Continue with GitHub",
            "Sign in",
            "Sign In",
            "Welcome back",
        ]:
            try:
                if page.locator(f"text={locator_text}").first.is_visible(timeout=2000):
                    return True
            except Exception:
                pass

        try:
            if page.locator("input[type='email' i], input[type='password' i], input[name*='email' i], input[name*='password' i]").first.is_visible(timeout=2000):
                return True
        except Exception:
            pass

        try:
            if page.locator("input[type='text' i]").first.is_visible(timeout=2000) and page.locator("input[type='password' i]").first.is_visible(timeout=2000):
                return True
        except Exception:
            pass

        return False

    def _read_random_input(self):
        possible_paths = [
            Path(__file__).resolve().parent / "inputs.txt",
            Path.cwd() / "inputs.txt",
            Path.home() / "AppData" / "Local" / "IBM CuratorAI" / "inputs.txt",
        ]

        for input_path in possible_paths:
            if input_path.exists():
                lines = [line.strip() for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                if lines:
                    return random.choice(lines)
                raise ValueError(f"inputs.txt is empty at {input_path}")

        raise FileNotFoundError("Missing inputs.txt. Add it next to the app or in AppData\\Local\\IBM CuratorAI.")

    def _check_session_status(self):
        self.status_var.set("Checking saved session...")
        self._append_log("Running a headless session check against the IBM app...")

        def _run_check():
            profile_dir = self._ensure_profile_dir(self.profile_var.get())
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir),
                        headless=True,
                        viewport={"width": 1440, "height": 980},
                        args=["--disable-dev-shm-usage"],
                    )
                    page = browser.new_page()
                    if not self._load_page_with_retries(page, self.url_var.get(), "Session check navigation"):
                        self.status_var.set("Session check unavailable - network issue")
                        return
                    page.wait_for_timeout(3000)

                    is_valid = self._is_logged_in_success_page(page)
                    browser.close()

                    if is_valid:
                        self.status_var.set("Session valid")
                        self._append_log("Saved IBM session is still valid in the persistent profile.")
                    else:
                        self.status_var.set("Session expired")
                        self._append_log("Headless check detected the login page or a reset session. Please re-login manually.")
                        self.after(0, lambda: self._show_login_required_dialog(
                            "Your IBM session appears to have expired or was reset.\n\n"
                            "A headless check found the login screen instead of the active chat page.\n"
                            "Please sign in again in the visible browser window so the saved session can be refreshed.",
                            on_continue=self._open_manual_login_for_session_check,
                        ))
            except Exception as exc:
                self.status_var.set("Session check failed")
                self._append_log(f"Session validation failed: {exc}")

        threading.Thread(target=_run_check, daemon=True).start()

    def _wait_for_app_ready(self, page):
        try:
            page.wait_for_load_state("domcontentloaded", timeout=PAGE_TIMEOUT_SECONDS * 1000)
        except Exception:
            pass

        deadline = time.time() + PAGE_TIMEOUT_SECONDS
        while time.time() < deadline:
            for selector in [
                "text=IBM Consulting Advantage",
                "text=History",
                "button:has-text('New Chat')",
                CHAT_TEXTAREA_SELECTOR,
                CHAT_TEXTAREA_FALLBACK_SELECTOR,
                "div[role='textbox']",
                "div[contenteditable='true']",
            ]:
                try:
                    if page.locator(selector).first.is_visible(timeout=1500):
                        return True
                except Exception:
                    continue
            page.wait_for_timeout(1000)

        return False

    def _find_chat_box(self, page):
        selectors = [
            CHAT_TEXTAREA_SELECTOR,
            CHAT_TEXTAREA_FALLBACK_SELECTOR,
            "textarea[placeholder*='Message']",
            "textarea[aria-label*='Message']",
            "[role='textbox']",
            "div[contenteditable='true']",
            "div[contenteditable='true'][aria-label*='chat']",
        ]

        for selector in selectors:
            try:
                locator = page.locator(selector).last
                if locator.count() > 0 and locator.is_visible(timeout=5000):
                    return locator
            except Exception:
                pass

        return None

    def _wait_for_chat_ready(self, page):
        deadline = time.time() + SELECTOR_TIMEOUT_SECONDS
        while time.time() < deadline:
            for selector in [CHAT_TEXTAREA_SELECTOR, CHAT_TEXTAREA_FALLBACK_SELECTOR]:
                try:
                    if page.locator(selector).first.is_visible(timeout=1500):
                        return True
                except Exception:
                    continue
            page.wait_for_timeout(500)
        return False

    def _find_send_button(self, page):
        selectors = [
            CHAT_SUBMIT_BUTTON_SELECTOR,
            'button[aria-label*="Send" i]',
            'button[title*="Send" i]',
            'button[data-testid*="send" i]',
            'button:has-text("Send")',
            'button:has(svg)',
        ]

        for selector in selectors:
            try:
                button = page.locator(selector).first
                if button.count() > 0 and button.is_visible(timeout=2000):
                    return button
            except Exception:
                continue

        return None

    def _assistant_response_count(self, page):
        selectors = [
            "[data-message-author-role='assistant']",
            "[data-testid*='assistant' i]",
            "[data-testid*='message' i][data-role='assistant']",
            "article[data-role='assistant']",
        ]

        for selector in selectors:
            try:
                locator = page.locator(selector)
                count = locator.count()
                if count:
                    return locator, count
            except Exception:
                continue

        return None, 0

    def _wait_for_chat_response(self, page, response_count_before_send):
        deadline = time.time() + RESPONSE_TIMEOUT_SECONDS
        last_text = ""
        stable_checks = 0

        while time.time() < deadline:
            locator, response_count = self._assistant_response_count(page)
            if locator is not None and response_count > response_count_before_send:
                try:
                    response_text = locator.last.inner_text(timeout=2000).strip()
                except Exception:
                    response_text = ""

                if response_text:
                    if response_text == last_text:
                        stable_checks += 1
                    else:
                        last_text = response_text
                        stable_checks = 0

                    if stable_checks >= 2:
                        self._append_log("ICA response received.")
                        return True

            page.wait_for_timeout(1000)

        self._append_log(f"No completed ICA response detected within {RESPONSE_TIMEOUT_SECONDS} seconds.")
        return False

    def _human_type(self, locator, text):
        locator.click()
        # Typed text is intentionally a little imperfect to mimic a human rhythm.
        # Tiny mistakes are inserted and then corrected within the same burst.
        i = 0
        while i < len(text):
            ch = text[i]
            locator.press(ch)
            time.sleep(random.uniform(0.04, 0.12))

            if random.random() < 0.03:
                # Small human-like typo: insert an accidental extra character and then backspace.
                extra = random.choice([" ", "e", "a", "s", "t", "o", "n", "i"]) if random.random() < 0.7 else "m"
                locator.press(extra)
                time.sleep(random.uniform(0.03, 0.07))
                locator.press("Backspace")
                time.sleep(random.uniform(0.03, 0.08))

            if random.random() < 0.02:
                # Pause naturally in the middle of a sentence.
                time.sleep(random.uniform(0.12, 0.26))

            i += 1

    def _submit_chat_prompt(self, page):
        prompt = self._read_random_input()
        self._append_log(f"Sending prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")

        if not self._wait_for_chat_ready(page):
            self._append_log("Chat box did not become visible in time. Aborting before sending the prompt.")
            raise RuntimeError("Chat box not ready")

        chat_box = self._find_chat_box(page)
        if chat_box is None:
            self._append_log("Could not find chat input. Please verify the page layout.")
            raise RuntimeError("Chat input not found")

        _, response_count_before_send = self._assistant_response_count(page)

        try:
            chat_box.wait_for(state="visible", timeout=SELECTOR_TIMEOUT_SECONDS * 1000)
            chat_box.click()
            chat_box.fill("")
            self._human_type(chat_box, prompt)

            send_button = self._find_send_button(page)
            if send_button is not None:
                send_button.click()
            else:
                page.keyboard.press("Enter")

            self._append_log("Prompt submitted successfully.")
            if self.wait_for_response_var.get():
                self.status_var.set("Waiting for ICA response...")
                self._append_log(f"Waiting up to {RESPONSE_TIMEOUT_SECONDS} seconds for the ICA response.")
                self._wait_for_chat_response(page, response_count_before_send)
            return prompt
        except Exception:
            self._append_log("Chat input was found but typing or sending failed. Retrying with a fallback approach.")
            try:
                chat_box.fill("")
                self._human_type(chat_box, prompt)

                send_button = self._find_send_button(page)
                if send_button is not None:
                    send_button.click()
                else:
                    page.keyboard.press("Enter")

                self._append_log("Fallback prompt submission succeeded.")
                return prompt
            except Exception:
                self._append_log("Could not send the prompt reliably. Please inspect the IBM chat page layout.")
                raise

    def _toggle_scheduler(self):
        if self.scheduler_var.get():
            self._start_scheduler()
        else:
            self._stop_scheduler()

    def _start_scheduler(self):
        if self._scheduler_thread is not None and self._scheduler_thread.is_alive():
            return

        try:
            interval_minutes = float(self.interval_var.get())
        except ValueError:
            self._append_log("Scheduler interval must be a number.")
            self.scheduler_var.set(False)
            return

        if interval_minutes <= 0:
            self._append_log("Scheduler interval must be greater than 0 minutes.")
            self.scheduler_var.set(False)
            return

        self._scheduler_stop.clear()
        schedule.clear()
        schedule.every(interval_minutes).minutes.do(self._start_background_run)
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        self.status_var.set(f"Scheduler active: every {interval_minutes} minutes")
        self._append_log(f"Scheduler started for every {interval_minutes} minutes.")

    def _scheduler_loop(self):
        while not self._scheduler_stop.is_set():
            schedule.run_pending()
            time.sleep(1)

    def _stop_scheduler(self):
        self._scheduler_stop.set()
        schedule.clear()
        self.scheduler_var.set(False)
        self.status_var.set("Ready")
        self._append_log("Scheduler stopped.")

    def _start_background_run(self):
        if self._run_lock.locked():
            self._append_log("Previous run is still in progress. Skipping this trigger.")
            return

        thread = threading.Thread(target=self._visit_site, daemon=True)
        thread.start()

    def _visit_site(self):
        with self._run_lock:
            self.status_var.set("Launching browser...")
            self._append_log("Opening persistent browser profile...")

            profile_dir = self._ensure_profile_dir(self.profile_var.get())
            self._append_log(f"Using browser profile: {profile_dir}")

            if self.first_run:
                self._append_log("First run detected. Switching to visible browser mode so the initial IBM sign-in can be completed.")
                self.headless_var.set(False)
                self.status_var.set("First run - signing in")
                headless_mode = False
            else:
                headless_mode = self.headless_var.get()

            try:
                with sync_playwright() as playwright:
                    while True:
                        browser_args = ["--disable-dev-shm-usage"]
                        if not headless_mode:
                            browser_args.extend([
                                "--window-size=1600,980",
                                "--force-device-scale-factor=1",
                            ])

                        browser = playwright.chromium.launch_persistent_context(
                            user_data_dir=str(profile_dir),
                            headless=headless_mode,
                            viewport={"width": 1600, "height": 980} if not headless_mode else {"width": 1460, "height": 980},
                            args=browser_args,
                        )

                        page = browser.new_page()
                        if not self._load_page_with_retries(page, self.url_var.get(), "Opening IBM app"):
                            self.status_var.set("Visit unavailable - network issue")
                            self._append_log("Could not reach the IBM app after retries. Please check your connection and try again.")
                            return

                        if not self._wait_for_app_ready(page):
                            self._append_log("IBM app shell did not finish loading. Waiting a bit longer before deciding the page is ready.")
                            time.sleep(5)

                        if self._is_logged_in_success_page(page):
                            self._append_log("Successful IBM session detected. Sending a random prompt from inputs.txt.")
                            self.status_var.set("Sending chat prompt...")
                            try:
                                self._submit_chat_prompt(page)
                            except Exception:
                                self._append_log("Prompt submission failed. The browser will still close after the failed attempt.")

                            self._append_log("Browser will close in 2 seconds after the chat action.")
                            time.sleep(2)
                            browser.close()
                            break

                        if self._is_login_page(page):
                            if headless_mode:
                                self._append_log("IBM login screen detected. Switching to headed mode for manual sign-in.")
                                self.status_var.set("Manual login required")
                                self.headless_var.set(False)
                                self.after(0, self._show_login_required_dialog)
                                browser.close()
                                headless_mode = False
                                continue

                            self._append_log("IBM login screen detected. Please complete the sign-in manually in the visible browser window.")
                            self.status_var.set("Waiting for manual IBM login...")
                            self.after(0, self._show_login_required_dialog)

                            deadline = time.time() + MAX_LOGIN_WAIT_SECONDS
                            while time.time() < deadline:
                                self._load_page_with_retries(page, action="Refreshing IBM login page")

                                if self._is_logged_in_success_page(page):
                                    self._append_log("Authentication detected. Sending a random prompt from inputs.txt.")
                                    self.status_var.set("Sending chat prompt...")
                                    try:
                                        self._submit_chat_prompt(page)
                                    except Exception:
                                        self._append_log("Prompt submission failed after login. Browser will close after the failed attempt.")

                                    self._append_log("Browser will close in 2 seconds after the chat action.")
                                    time.sleep(2)
                                    browser.close()
                                    break

                                if not self._is_login_page(page):
                                    self._append_log("Manual sign-in completed. Sending a random prompt from inputs.txt.")
                                    self.status_var.set("Sending chat prompt...")
                                    try:
                                        self._submit_chat_prompt(page)
                                    except Exception:
                                        self._append_log("Prompt submission failed after manual sign-in. Browser will close after the failed attempt.")

                                    self._append_log("Browser will close in 2 seconds after the chat action.")
                                    time.sleep(2)
                                    browser.close()
                                    break

                                time.sleep(5)
                            else:
                                self._append_log("Manual IBM login timed out. Please sign in and run the script again.")
                                browser.close()
                                break

                            break

                        self._append_log(f"Page loaded successfully: {self.url_var.get()}")
                        self.status_var.set("Visit completed successfully")
                        time.sleep(2)
                        browser.close()
                        break

                self.status_var.set("Visit completed successfully")
                self._append_log("The browser session closed cleanly. Login details will now be saved in the browser profile for future runs.")
            except Exception as exc:
                self.status_var.set("Visit failed")
                self._append_log(f"Error: {exc}")


if __name__ == "__main__":
    app = BrowserAutomationApp()
    app.mainloop()
