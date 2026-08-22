#!/usr/bin/env python3
"""Discord Badge Spoofer - Standalone Desktop Launcher & Science Event Engine

No third-party packages are required: uses Python's built-in modules (tkinter, urllib, json, dataclasses).
Run with ``python main.py`` or double-click ``start.bat`` on Windows.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Iterator, Sequence

def _get_app_dir() -> Path:
    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
    else:
        base = Path.home() / ".config"
    dir_path = base / "DiscordBadgeSpoofer"
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path

# Constants & Paths
ROOT = Path(__file__).resolve().parent
APP_DIR = _get_app_dir()
GAMES_FILE = APP_DIR / "data" / "games.json"
STATE_FILE = APP_DIR / "science_state.json"

ME_URL = "https://discord.com/api/v9/users/@me?with_analytics_token=true"
SCIENCE_URL = "https://discord.com/api/v9/science"
PROPERTIES_URL = "https://cordapi.dolfi.es/api/v2/properties/windows"
GAMES_CDN_URL = "https://cdn.discordapp.com/detectables/games.json"

BATCH_SIZE = 50
BATCH_DELAY = 0.3
AUTH_MAX_AGE = 12 * 3600
DEBUG = False

CLIENT_VERSION = "1.0.9253"
CLIENT_BUILD_NUMBER = 594031
NATIVE_BUILD_NUMBER = 88414
OS_VERSION = "10.0.26200"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) discord/1.0.9253 Chrome/148.0.7778.280 "
    "Electron/42.7.1 Safari/537.36"
)

# UI Styling Tokens
BG = "#0A0B12"
PANEL = "#12141E"
PANEL_ALT = "#191C28"
BORDER = "#292D3E"
TEXT = "#F4F5FA"
MUTED = "#9299AD"
ACCENT = "#7C5CFC"
ACCENT_HOVER = "#947BFF"
SUCCESS = "#43D69E"
WARNING = "#F4B860"
DANGER = "#FF6B7A"
FONT = "Segoe UI"


@dataclass
class State:
    token: str = ""
    cookie: str = ""
    fingerprint: str = ""
    analytics_token: str = ""
    fetched_at: int = 0
    used_games: list[str] = None
    total_games_claimed: int = 0
    total_hours_claimed: float = 0.0

    def __post_init__(self) -> None:
        if self.used_games is None:
            self.used_games = []

    @classmethod
    def load(cls) -> "State":
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            state = cls(**{k: data.get(k, v) for k, v in cls().__dict__.items() if k != "used_games"})
            state.used_games = data.get("used_games", [])
            return state
        return cls()

    def save(self) -> None:
        STATE_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @property
    def is_stale(self) -> bool:
        return not self.analytics_token or (time.time() - self.fetched_at) > AUTH_MAX_AGE

    @property
    def has_cookie(self) -> bool:
        return bool(self.cookie.strip())

    @property
    def has_token(self) -> bool:
        return bool(self.token.strip())


def _local_props() -> dict:
    return {
        "os": "Windows",
        "browser": "Discord Client",
        "release_channel": "stable",
        "client_version": CLIENT_VERSION,
        "os_version": OS_VERSION,
        "os_arch": "x64",
        "app_arch": "x64",
        "system_locale": "en-GB",
        "has_client_mods": False,
        "browser_user_agent": USER_AGENT,
        "browser_version": "42.7.1",
        "os_sdk_version": "26200",
        "client_build_number": CLIENT_BUILD_NUMBER,
        "native_build_number": NATIVE_BUILD_NUMBER,
        "client_event_source": None,
        "client_app_state": "focused",
    }


def build_super_props(launch_signature: str, heartbeat_session: str) -> str:
    try:
        req = urllib.request.Request(PROPERTIES_URL, method="POST", data=b"{}",
                                     headers={"content-type": "application/json", "user-agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as response:
            props = json.loads(response.read().decode("utf-8"))["properties"]
    except Exception:
        props = _local_props()
    props["client_launch_id"] = str(uuid.uuid4())
    props["launch_signature"] = launch_signature
    props["client_heartbeat_session_id"] = heartbeat_session
    raw = json.dumps(props, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _read_analytics_token(auth_token: str, super_props: str) -> str:
    req = urllib.request.Request(ME_URL, headers={
        "authorization": auth_token,
        "user-agent": USER_AGENT,
        "x-super-properties": super_props,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"token rejected ({exc.code})") from exc
    token = data.get("analytics_token")
    if not token:
        raise RuntimeError("no analytics_token in response")
    return token


def ensure_token(state: State, super_props: str) -> None:
    if not state.is_stale:
        return
    state.analytics_token = _read_analytics_token(state.token, super_props)
    state.fetched_at = int(time.time())
    state.save()


@dataclass(frozen=True)
class Session:
    heartbeat_session: str
    launch_signature: str
    super_props: str

    @classmethod
    def new(cls) -> "Session":
        hb = str(uuid.uuid4())
        sig = str(uuid.uuid4())
        return cls(hb, sig, build_super_props(sig, hb))


@dataclass(frozen=True)
class Game:
    id: str
    name: str
    exe: str


def _win_exe(game: dict) -> str:
    for entry in game.get("executables", []):
        if entry.get("os") == "win32" and entry.get("name"):
            return entry["name"]
    return "game.exe"


def _download_games() -> str:
    request = urllib.request.Request(GAMES_CDN_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
    try:
        GAMES_FILE.parent.mkdir(parents=True, exist_ok=True)
        GAMES_FILE.write_text(raw, encoding="utf-8")
    except OSError:
        pass
    return raw


def _parse_games(raw: str) -> list[Game]:
    data = json.loads(raw)
    games: list[Game] = []
    seen: set[str] = set()
    for entry in data:
        gid = str(entry.get("id", ""))
        if not gid.isdigit() or gid in seen:
            continue
        if not any(e.get("os") == "win32" and e.get("name") for e in entry.get("executables", [])):
            continue
        seen.add(gid)
        games.append(Game(gid, entry.get("name", "Unknown"), _win_exe(entry)))
    return games


def load_games() -> list[Game]:
    raw = ""
    if GAMES_FILE.exists():
        raw = GAMES_FILE.read_text(encoding="utf-8").strip()
    if raw:
        try:
            games = _parse_games(raw)
            if games:
                return games
        except (json.JSONDecodeError, ValueError):
            pass
    try:
        return _parse_games(_download_games())
    except Exception:
        return []


def _chunked(items: Sequence[Game], size: int) -> Iterator[Sequence[Game]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


class ScienceClient:
    def __init__(self, state: State, session: Session) -> None:
        self.state = state
        self.session = session
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def build_launch(self, game: Game) -> dict:
        now = int(time.time() * 1000)
        props = {
            "client_track_timestamp": now,
            "client_heartbeat_session_id": self.session.heartbeat_session,
            "event_sequence_number": self._next_seq(),
            "game": game.name,
            "game_id": game.id,
            "verified": True,
            "elevated": False,
            "is_launcher": False,
            "game_platform": "desktop",
            "detection_method": "verified_game",
            "is_overlay_enabled": False,
            "is_overlay_game_enabled": True,
            "is_overlay_game_source": "OOP_DEFAULT_DATABASE",
            "fullscreen_type": "UNKNOWN",
            "hardware_display_count": 1,
            "overlay_method": "Disabled",
            "activity_status_enabled": True,
            "activity_status_shared_guilds": [],
            "current_user_status": "online",
            "game_detection_enabled": True,
            "executable_path": game.exe,
            "voice_channel_id": None,
            "voice_channel_type": None,
            "voice_channel_bitrate": None,
            "voice_channel_guild_id": None,
            "hidden_by_distributor": False,
            "game_metadata": None,
            "client_performance_cpu": None,
            "client_performance_memory": None,
            "cpu_core_count": None,
            "accessibility_features": 0,
            "rendered_locale": "en-GB",
            "launch_signature": self.session.launch_signature,
            "client_rtc_state": None,
            "client_app_state": "focused",
            "client_send_timestamp": now,
        }
        return {"type": "launch_game", "properties": props}

    def build_heartbeat(self, game: Game, duration_ms: int, session_id: str,
                        initial: bool, final: bool, ts: int | None = None) -> dict:
        ts = int(time.time() * 1000) if ts is None else ts
        return {
            "type": "running_game_heartbeat",
            "properties": {
                "client_track_timestamp": ts,
                "client_heartbeat_session_id": self.session.heartbeat_session,
                "event_sequence_number": self._next_seq(),
                "game_id": game.id,
                "game_name": game.name,
                "game_metadata": None,
                "game_executable": game.exe,
                "game_detection_enabled": True,
                "initial_heartbeat": initial,
                "final_heartbeat": final,
                "game_session_id": session_id,
                "duration_tracked_ms": duration_ms,
                "rtc_connection_id": None,
                "media_session_id": None,
                "launch_signature": self.session.launch_signature,
                "client_app_state": "focused",
                "client_send_timestamp": ts,
            },
        }

    def build_session(self, game: Game, duration_ms: int) -> list[dict]:
        sid = str(uuid.uuid4())
        now = int(time.time() * 1000)
        start = now - duration_ms
        if start < 0:
            start = now
        return [
            self.build_heartbeat(game, 0, sid, initial=True, final=False, ts=start),
            self.build_launch(game),
            self.build_heartbeat(game, duration_ms, sid, initial=False, final=True, ts=now),
        ]

    def post(self, events: Sequence[dict]) -> int:
        payload = {"token": self.state.analytics_token, "events": list(events)}
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "accept": "*/*",
            "accept-language": "en-GB",
            "authorization": self.state.token,
            "content-type": "application/json",
            "cookie": self.state.cookie,
            "origin": "https://discord.com",
            "referer": "https://discord.com/channels/@me",
            "user-agent": USER_AGENT,
            "x-debug-options": "bugReporterEnabled",
            "x-discord-locale": "en-GB",
            "x-discord-timezone": "Europe/Oslo",
            "x-super-properties": self.session.super_props,
        }
        if DEBUG:
            print("\n" + "=" * 72)
            print(f"POST {SCIENCE_URL} ({len(payload['events'])} events)")
            print("headers:", json.dumps(headers, indent=2))
            print("body:", json.dumps(payload, indent=2))
            print("=" * 72)
        request = urllib.request.Request(SCIENCE_URL, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code
        except Exception:
            return 0


class HelpModal(tk.Toplevel):
    def __init__(self, parent: tk.Tk, title: str, steps: list[str], code_snippet: str = "") -> None:
        super().__init__(parent)
        self.title(title)
        self.configure(bg=BG)
        self.overrideredirect(True)
        self.transient(parent)
        self.grab_set()

        width, height = 640, 480
        self.geometry(f"{width}x{height}")

        try:
            px = parent.winfo_x() + (parent.winfo_width() // 2) - (width // 2)
            py = parent.winfo_y() + (parent.winfo_height() // 2) - (height // 2)
            self.geometry(f"{width}x{height}+{max(0, px)}+{max(0, py)}")
        except Exception:
            pass

        # Outer border frame
        outer = tk.Frame(self, bg=BG, highlightbackground=BORDER, highlightthickness=1)
        outer.pack(fill="both", expand=True)

        container = tk.Frame(outer, bg=BG, padx=24, pady=20)
        container.pack(fill="both", expand=True)

        hdr = tk.Frame(container, bg=BG, cursor="fleur")
        hdr.pack(fill="x", pady=(0, 16))

        def _start_drag(event):
            self._drag_x = event.x
            self._drag_y = event.y

        def _do_drag(event):
            x = self.winfo_x() + (event.x - self._drag_x)
            y = self.winfo_y() + (event.y - self._drag_y)
            self.geometry(f"+{x}+{y}")

        hdr.bind("<Button-1>", _start_drag)
        hdr.bind("<B1-Motion>", _do_drag)

        tk.Label(hdr, text="✦", bg=BG, fg=ACCENT, font=(FONT, 18, "bold")).pack(side="left", padx=(0, 10))
        tk.Label(hdr, text=title, bg=BG, fg=TEXT, font=(FONT, 14, "bold")).pack(side="left")

        close_btn = tk.Button(
            hdr, text="✕", command=self.destroy, bg=PANEL_ALT, fg=MUTED,
            activebackground=DANGER, activeforeground=TEXT, relief="flat", bd=0,
            font=(FONT, 11, "bold"), cursor="hand2", padx=10, pady=4
        )
        close_btn.pack(side="right")

        card = tk.Frame(container, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, padx=22, pady=18)
        card.pack(fill="both", expand=True, pady=(0, 16))

        for idx, step_text in enumerate(steps, start=1):
            step_frame = tk.Frame(card, bg=PANEL)
            step_frame.pack(fill="x", pady=6, anchor="w")

            num_lbl = tk.Label(
                step_frame, text=f"Step {idx}", bg=PANEL_ALT, fg=ACCENT_HOVER,
                font=(FONT, 8, "bold"), padx=8, pady=3
            )
            num_lbl.pack(side="left", padx=(0, 12))

            txt_lbl = tk.Label(
                step_frame, text=step_text, bg=PANEL, fg=TEXT,
                font=(FONT, 9), wraplength=460, justify="left"
            )
            txt_lbl.pack(side="left", fill="x", expand=True)

        if code_snippet:
            snip_frame = tk.Frame(card, bg="#0A0C14", highlightbackground=BORDER, highlightthickness=1, padx=12, pady=10)
            snip_frame.pack(fill="x", pady=(14, 4))

            top_snip = tk.Frame(snip_frame, bg="#0A0C14")
            top_snip.pack(fill="x", pady=(0, 6))

            tk.Label(top_snip, text="CONSOLE SCRIPT", bg="#0A0C14", fg=MUTED, font=(FONT, 8, "bold")).pack(side="left")

            def copy_code():
                self.clipboard_clear()
                self.clipboard_append(code_snippet)
                copy_btn.configure(text="✓ Copied!", fg=SUCCESS)
                self.after(2000, lambda: copy_btn.configure(text="Copy Code", fg=ACCENT_HOVER))

            copy_btn = tk.Button(
                top_snip, text="Copy Code", command=copy_code, bg=PANEL_ALT, fg=ACCENT_HOVER,
                activebackground=ACCENT, activeforeground=TEXT, relief="flat", bd=0,
                font=(FONT, 8, "bold"), cursor="hand2", padx=8, pady=2
            )
            copy_btn.pack(side="right")

            entry = tk.Entry(
                snip_frame, bg="#0A0C14", fg=SUCCESS, readonlybackground="#0A0C14",
                disabledbackground="#0A0C14", disabledforeground=SUCCESS,
                selectbackground=ACCENT, selectforeground=TEXT,
                insertbackground=TEXT, relief="flat", bd=0, font=("Consolas", 9)
            )
            entry.insert(0, code_snippet)
            entry.configure(state="readonly")
            entry.pack(fill="x", ipady=4)

            def select_all(event=None):
                entry.focus()
                entry.selection_range(0, tk.END)

            entry.bind("<Button-1>", select_all)

        btn_frame = tk.Frame(container, bg=BG)
        btn_frame.pack(fill="x", side="bottom")

        ok_btn = tk.Button(
            btn_frame, text="Got it", command=self.destroy, bg=ACCENT, fg=TEXT,
            activebackground=ACCENT_HOVER, activeforeground=TEXT, relief="flat", bd=0,
            cursor="hand2", padx=26, pady=9, font=(FONT, 10, "bold")
        )
        ok_btn.pack(side="right")


class Launcher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Discord Badge Spoofer")
        self.geometry("1140x780")
        self.minsize(980, 700)
        self.configure(bg=BG)

        ICON_FILE = ROOT / "assets" / "icon.ico"
        if not ICON_FILE.exists():
            ICON_FILE = ROOT / "icon.ico"
        if ICON_FILE.exists():
            try:
                self.iconbitmap(str(ICON_FILE))
            except Exception:
                pass

        self.state = State.load()
        self.games: list[Game] = []
        self.session: Session | None = None
        self.client: ScienceClient | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False

        self.token_var = tk.StringVar(value=self.state.token)
        self.cookie_var = tk.StringVar(value=self.state.cookie)
        self.games_var = tk.StringVar(value="50")
        self.hours_per_game_var = tk.StringVar(value="1.0")
        self.calc_preview_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Preparing")
        self.stat_claimed = tk.StringVar(value=f"{self.state.total_games_claimed:,}")
        self.stat_hours = tk.StringVar(value=f"{self.state.total_hours_claimed:,.0f} h")
        self.notice_var = tk.StringVar(value="Enter your token and cookie credentials to connect.")

        self.games_var.trace_add("write", self._update_calc_preview)
        self.hours_per_game_var.trace_add("write", self._update_calc_preview)
        self._update_calc_preview()

        self._configure_style()
        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(80, self._drain_events)
        self.after(180, self.prepare)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Accent.Horizontal.TProgressbar",
            troughcolor=PANEL_ALT,
            background=ACCENT,
            bordercolor=PANEL_ALT,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=8,
        )

    @staticmethod
    def _label(parent: tk.Misc, text: str, size: int = 10, color: str = TEXT,
               weight: str = "normal", **kwargs: object) -> tk.Label:
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=(FONT, size, weight), **kwargs)

    def _card(self, parent: tk.Misc, **kwargs: object) -> tk.Frame:
        return tk.Frame(parent, bg=PANEL, highlightbackground=BORDER,
                        highlightthickness=1, **kwargs)

    def _button(self, parent: tk.Misc, text: str, command, kind: str = "accent") -> tk.Button:
        colors = {
            "accent": (ACCENT, ACCENT_HOVER, TEXT),
            "quiet": (PANEL_ALT, "#222638", TEXT),
            "danger": ("#48212C", "#5A2936", "#FFC6CD"),
        }
        base, hover, foreground = colors[kind]
        button = tk.Button(parent, text=text, command=command, bg=base, fg=foreground,
                           activebackground=hover, activeforeground=foreground,
                           relief="flat", bd=0, cursor="hand2", padx=18, pady=11,
                           font=(FONT, 10, "bold"), highlightthickness=0)
        button.bind("<Enter>", lambda _event: button.configure(bg=hover))
        button.bind("<Leave>", lambda _event: button.configure(bg=base))
        return button

    def _help_link(self, parent: tk.Misc, command) -> tk.Label:
        lbl = tk.Label(parent, text="(How to find?)", bg=parent.cget("bg"), fg=ACCENT_HOVER,
                       font=(FONT, 8, "underline"), cursor="hand2")
        lbl.bind("<Button-1>", lambda _e: command())
        return lbl

    def _entry(self, parent: tk.Misc, variable: tk.StringVar, show: str = "") -> tk.Entry:
        return tk.Entry(parent, textvariable=variable, show=show, bg="#0E1018", fg=TEXT,
                        insertbackground=TEXT, relief="flat", bd=0, font=(FONT, 10),
                        highlightthickness=1, highlightbackground=BORDER,
                        highlightcolor=ACCENT)

    def _update_calc_preview(self, *args) -> None:
        try:
            c = int(self.games_var.get().strip())
            h = float(self.hours_per_game_var.get().strip())
            if c > 0 and h > 0:
                tot = c * h
                self.calc_preview_var.set(f"Total duration to process: {tot:,.1f} hours ({c} games × {h:g} h/game)")
                return
        except ValueError:
            pass
        self.calc_preview_var.set("Please enter a valid number of games and hours per game.")

    def _refresh_stats_display(self) -> None:
        self.stat_claimed.set(f"{self.state.total_games_claimed:,}")
        self.stat_hours.set(f"{self.state.total_hours_claimed:,.0f} h")

    def _show_token_help(self) -> None:
        title = "How to find your Discord Token"
        steps = [
            "Open Discord in your browser (discord.com/app) or desktop client.",
            "Press F12 (or Ctrl + Shift + I) to open Developer Tools.",
            "Switch to the Network tab.",
            "Click on any request (e.g., '/science', 'messages', or '@me').",
            "Under Request Headers, locate the 'Authorization' header.",
            "Copy the entire Authorization value and paste it into the ACCOUNT TOKEN field."
        ]
        HelpModal(self, title, steps)

    def _show_cookie_help(self) -> None:
        title = "How to find cf_clearance Cookie"
        steps = [
            "Open Discord in your web browser (discord.com/app).",
            "Press F12 (or Ctrl + Shift + I) to open Developer Tools.",
            "Method 1 (Application Tab): Go to Application tab -> Storage -> Cookies -> https://discord.com -> Find 'cf_clearance' and copy its Value.",
            "Method 2 (Network Tab): Go to Network tab -> Filter by '/science' -> Click any request -> Copy the 'cookie' header value under Request Headers.",
            "Paste the value (e.g., cf_clearance=YOUR_VALUE) into the CF_CLEARANCE COOKIE field."
        ]
        HelpModal(self, title, steps)

    def _build_layout(self) -> None:
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True)

        top = tk.Frame(main, bg=BG)
        top.pack(fill="x", padx=52, pady=(28, 14))
        tk.Label(top, text="✦", bg=BG, fg=ACCENT, font=(FONT, 24, "bold")).pack(side="left", padx=(0, 11))
        heading = tk.Frame(top, bg=BG)
        heading.pack(side="left")
        self._label(heading, "Discord Badge Spoofer", 23, TEXT, "bold").pack(anchor="w")
        self._label(heading, "Automated activity & hour spoofer for Discord Science events.", 10, MUTED).pack(anchor="w", pady=(3, 0))

        status = tk.Frame(top, bg="#182B28", highlightbackground="#285648", highlightthickness=1)
        status.pack(side="right", pady=8)
        tk.Label(status, text="●", bg="#182B28", fg=SUCCESS, font=(FONT, 10, "bold")).pack(side="left", padx=(11, 5), pady=7)
        tk.Label(status, textvariable=self.status_var, bg="#182B28", fg="#A8E9CF", font=(FONT, 9, "bold")).pack(side="left", padx=(0, 11), pady=7)

        connect = self._card(main)
        connect.pack(fill="x", padx=52)
        self._label(connect, "Authentication", 14, TEXT, "bold").grid(row=0, column=0, columnspan=3, sticky="w", padx=22, pady=(16, 1))
        self._label(connect, "Enter your account token and Cloudflare cookie.", 9, MUTED).grid(row=1, column=0, columnspan=3, sticky="w", padx=22, pady=(0, 12))
        connect.grid_columnconfigure(0, weight=1)
        connect.grid_columnconfigure(1, weight=1)
        connect.grid_columnconfigure(2, weight=0)

        lbl_frame_token = tk.Frame(connect, bg=PANEL)
        lbl_frame_token.grid(row=2, column=0, sticky="w", padx=(22, 10))
        self._label(lbl_frame_token, "ACCOUNT TOKEN ", 8, MUTED, "bold").pack(side="left")
        self._help_link(lbl_frame_token, self._show_token_help).pack(side="left")

        lbl_frame_cookie = tk.Frame(connect, bg=PANEL)
        lbl_frame_cookie.grid(row=2, column=1, sticky="w", padx=(10, 10))
        self._label(lbl_frame_cookie, "CF_CLEARANCE COOKIE ", 8, MUTED, "bold").pack(side="left")
        self._help_link(lbl_frame_cookie, self._show_cookie_help).pack(side="left")

        self.token_entry = self._entry(connect, self.token_var, "•")
        self.token_entry.grid(row=3, column=0, sticky="ew", ipady=8, padx=(22, 10), pady=(5, 16))
        self.cookie_entry = self._entry(connect, self.cookie_var, "•")
        self.cookie_entry.grid(row=3, column=1, sticky="ew", ipady=8, padx=(10, 10), pady=(5, 16))

        self.connect_button = self._button(connect, "Connect & Load", self.prepare)
        self.connect_button.grid(row=3, column=2, padx=(8, 22), pady=(5, 16))

        stats = tk.Frame(main, bg=BG)
        stats.pack(fill="x", padx=52, pady=12)
        for index, (label, variable, accent, subtext) in enumerate((
            ("Total Games Processed", self.stat_claimed, SUCCESS, "Games logged by this launcher"),
            ("Total Hours Processed", self.stat_hours, WARNING, "Playtime logged by this launcher"),
        )):
            card = self._card(stats)
            card.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 9, 0))
            self._label(card, label.upper(), 8, MUTED, "bold").pack(anchor="w", padx=18, pady=(12, 2))
            tk.Label(card, textvariable=variable, bg=PANEL, fg=accent, font=(FONT, 20, "bold")).pack(anchor="w", padx=18)
            self._label(card, subtext, 8, MUTED).pack(anchor="w", padx=18, pady=(1, 12))
            stats.grid_columnconfigure(index, weight=1)

        action = self._card(main)
        action.pack(fill="x", padx=52, pady=(0, 8))
        self._label(action, "New Batch Operation", 15, TEXT, "bold").pack(anchor="w", padx=22, pady=(14, 2))
        self._label(action, "Specify the number of games and duration (hours) to log per game.", 9, MUTED).pack(anchor="w", padx=22)

        fields = tk.Frame(action, bg=PANEL)
        fields.pack(fill="x", padx=22, pady=(12, 6))
        for column in range(2):
            fields.grid_columnconfigure(column, weight=1)
        self._label(fields, "NUMBER OF GAMES", 8, MUTED, "bold").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._label(fields, "HOURS PER GAME", 8, MUTED, "bold").grid(row=0, column=1, sticky="w", padx=(8, 0))
        self._entry(fields, self.games_var).grid(row=1, column=0, sticky="ew", ipady=8, padx=(0, 8), pady=(5, 0))
        self._entry(fields, self.hours_per_game_var).grid(row=1, column=1, sticky="ew", ipady=8, padx=(8, 0), pady=(5, 0))

        calc_preview = tk.Label(action, textvariable=self.calc_preview_var, bg=PANEL, fg=ACCENT, font=(FONT, 9, "italic"))
        calc_preview.pack(anchor="w", padx=22, pady=(4, 0))

        self.progress = ttk.Progressbar(action, style="Accent.Horizontal.TProgressbar", mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=22, pady=(10, 4))
        self.progress_text = self._label(action, "Connect credentials before starting operation.", 9, MUTED)
        self.progress_text.pack(anchor="w", padx=22)
        self.run_button = self._button(action, "Start Operation  →", self.claim)
        self.run_button.pack(anchor="w", padx=22, pady=(12, 14))

        notice = tk.Label(main, textvariable=self.notice_var, bg=BG, fg=MUTED, font=(FONT, 9))
        notice.pack(anchor="w", padx=54, pady=(0, 10))

        footer = tk.Frame(main, bg=BG)
        footer.pack(fill="x", side="bottom", padx=54, pady=(0, 12))
        self._label(footer, "Created by DynaMarley", 9, ACCENT_HOVER, "bold").pack(side="left")
        self._label(footer, " · Discord Badge Spoofer v1.0", 9, MUTED).pack(side="left")

    def log_line(self, message: str, tag: str = "info") -> None:
        self.notice_var.set(message)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for button in (self.run_button, self.connect_button):
            button.configure(state=state)

    def _save_state_from_fields(self) -> bool:
        token = self.token_var.get().strip()
        cookie = self.cookie_var.get().strip()
        if not token or not cookie:
            messagebox.showwarning("Missing Credentials", "Account token and cf_clearance cookie are required to proceed.")
            return False
        token_changed = token != self.state.token
        self.state.token = token
        self.state.cookie = cookie
        if token_changed:
            self.state.analytics_token = ""
            self.state.fetched_at = 0
        self.state.save()
        return True

    def prepare(self) -> None:
        if self.busy:
            return
        if not self.token_var.get().strip() or not self.cookie_var.get().strip():
            self.status_var.set("Credentials required")
            self.log_line("Waiting for account token and cf_clearance cookie.", "warn")
            return
        if not self._save_state_from_fields():
            return
        self._set_busy(True)
        self.status_var.set("Preparing session")
        self.log_line("Loading game list and preparing session…")
        threading.Thread(target=self._prepare_worker, daemon=True).start()

    def _prepare_worker(self) -> None:
        try:
            games = load_games()
            if not games:
                raise RuntimeError("Failed to load games list.")
            session = Session.new()
            ensure_token(self.state, session.super_props)
            self.events.put(("ready", (games, session)))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def claim(self) -> None:
        if self.busy:
            return
        if not self._save_state_from_fields():
            return
        if not self.games or not self.client:
            self.prepare()
            return
        try:
            count = int(self.games_var.get().strip())
            hours_per_game = float(self.hours_per_game_var.get().strip())
            if count < 1 or hours_per_game <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid Value", "Number of games must be a positive integer and hours per game must be > 0.")
            return

        count = min(count, len(self.games))
        selected = self._select_games(count)
        if not selected:
            messagebox.showwarning("No Games Selected", "No games available for selection.")
            return

        total_hours = len(selected) * hours_per_game
        confirm_msg = (
            f"{len(selected)} games selected, logging {hours_per_game:g} hours per game.\n"
            f"Total duration to log: {total_hours:,.1f} hours.\n\n"
            f"Do you wish to continue?"
        )

        if not messagebox.askyesno("Confirm Operation", confirm_msg):
            return

        self._set_busy(True)
        self.progress.configure(value=0)
        self.status_var.set("Processing")
        self.log_line(f"Processing {len(selected)} games with {hours_per_game:g} hours per game (Total: {total_hours:,.1f} hours).")
        threading.Thread(target=self._claim_worker, args=(selected, hours_per_game), daemon=True).start()

    def _claim_worker(self, games: list[Game], hours: float) -> None:
        assert self.session is not None
        if self.state.is_stale:
            try:
                ensure_token(self.state, self.session.super_props)
            except Exception as exc:
                self.events.put(("auth_error", f"Failed to refresh token: {exc}"))
                return

        self.client = ScienceClient(self.state, self.session)
        completed = 0
        duration_ms = int(hours * 3_600_000)
        total = len(games)
        for request_no, chunk in enumerate(_chunked(games, BATCH_SIZE), start=1):
            events = []
            for game in chunk:
                events.extend(self.client.build_session(game, duration_ms))
            status = self.client.post(events)
            if status == 204:
                completed += len(chunk)
                self.events.put(("progress", (completed, total, f"Batch {request_no} completed · {completed}/{total} games")))
            elif status in (401, 403):
                self.events.put(("auth_error", f"Authentication rejected ({status}). Refresh credentials."))
                return
            else:
                self.events.put(("log", (f"Batch {request_no} response: HTTP {status}", "warn")))
            time.sleep(BATCH_DELAY)

        self.state.total_games_claimed += completed
        self.state.total_hours_claimed += completed * hours
        self.state.save()
        self.events.put(("complete", (completed, total, hours)))

    def _select_games(self, count: int) -> list[Game]:
        available_ids = {game.id for game in self.games}
        unused_ids = [game.id for game in self.games if game.id not in self.state.used_games]
        used_ids = [game_id for game_id in self.state.used_games if game_id in available_ids]
        if len(unused_ids) >= count:
            selected_ids = unused_ids[:count]
        else:
            selected_ids = unused_ids
            remaining = count - len(selected_ids)
            selected_ids.extend((used_ids[remaining:] + used_ids[:remaining])[:remaining])
        self.state.used_games = [game_id for game_id in self.state.used_games if game_id not in selected_ids] + selected_ids
        lookup = {game.id: game for game in self.games}
        return [lookup[game_id] for game_id in selected_ids if game_id in lookup]

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "ready":
                    self.games, self.session = payload  # type: ignore[misc]
                    self.client = ScienceClient(self.state, self.session)
                    self.status_var.set("Ready")
                    self.progress_text.configure(text="Connected and ready. Specify operation parameters below.")
                    self._refresh_stats_display()
                    self.log_line(f"Connection ready · {len(self.games):,} games available.", "ok")
                    self._set_busy(False)
                elif kind == "error":
                    self.status_var.set("Initialization failed")
                    self.log_line(str(payload), "error")
                    self._set_busy(False)
                elif kind == "progress":
                    completed, total, text = payload  # type: ignore[misc]
                    self.progress.configure(value=(completed / total) * 100)
                    self.progress_text.configure(text=text)
                    self.log_line(text, "ok")
                elif kind == "log":
                    text, tag = payload  # type: ignore[misc]
                    self.log_line(text, tag)
                elif kind == "auth_error":
                    self.status_var.set("Session required")
                    self.log_line(str(payload), "error")
                    self._set_busy(False)
                elif kind == "complete":
                    completed, total, hours = payload  # type: ignore[misc]
                    self.progress.configure(value=100)
                    self.progress_text.configure(text=f"Completed · {completed}/{total} games processed")
                    self._refresh_stats_display()
                    self.status_var.set("Completed")
                    self.log_line(f"Operation completed · {completed} games · {completed * hours:,.1f} hours logged.", "ok")
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.after(80, self._drain_events)

    def _close(self) -> None:
        if self.busy and not messagebox.askyesno("Exit", "An operation is currently in progress. Are you sure you want to exit?"):
            return
        self.destroy()


def main() -> None:
    Launcher().mainloop()


if __name__ == "__main__":
    main()
