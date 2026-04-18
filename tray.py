"""
Vibe tray — long-running system-tray app. Tails ~/.vibe/sessions.jsonl, maintains
per-session state, pops a toast on Stop, reflects aggregate state in the tray icon.

Run with:  pythonw tray.py   (pythonw hides the console window)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from PIL import Image, ImageDraw
import pystray

HOME = Path(os.path.expanduser("~"))
VIBE_DIR = HOME / ".vibe"
LOG_PATH = VIBE_DIR / "sessions.jsonl"
LOG_FILE = VIBE_DIR / "tray.log"

PILL_SCRIPT = Path(__file__).with_name("pill.py")
PYTHONW = Path(sys.executable).with_name("pythonw.exe")
if not PYTHONW.exists():
    PYTHONW = Path(sys.executable)  # fall back to the running interpreter

POLL_INTERVAL = 0.3       # seconds between log-tail reads
DONE_LINGER = 30.0        # seconds a finished session stays in the active map

COLORS = {
    "idle":    (90, 90, 100),
    "working": (0, 200, 255),
    "asking":  (255, 184, 0),
    "done":    (0, 217, 126),
    "error":   (255, 59, 48),
}


@dataclass
class Session:
    session_id: str
    cwd: str = ""
    status: str = "idle"          # idle | working | asking | done | error
    started_at: float = 0.0        # first SessionStart time
    prompt_started_at: float = 0.0 # last UserPromptSubmit time — basis for duration
    last_activity_at: float = 0.0
    done_at: Optional[float] = None

    @property
    def project_name(self) -> str:
        return Path(self.cwd).name if self.cwd else "(unknown)"

    def duration(self) -> float:
        end = self.done_at or time.time()
        start = self.prompt_started_at or self.started_at or end
        return max(0.0, end - start)


def log(msg: str) -> None:
    try:
        VIBE_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def fmt_duration(seconds: float) -> str:
    if seconds < 1:
        return "<1s"
    if seconds < 60:
        return f"{int(seconds)}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


def make_icon(color: tuple[int, int, int], badge: Optional[str] = None) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, size - 4, size - 4), fill=color + (255,))
    if badge:
        # tiny badge dot — used when multiple sessions are active
        draw.ellipse((size - 22, 4, size - 4, 22), fill=(255, 255, 255, 230))
    return img


class VibeTray:
    def __init__(self) -> None:
        self.sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.icon = pystray.Icon(
            "vibe",
            make_icon(COLORS["idle"]),
            "Vibe · idle",
            menu=self._build_menu(),
        )

    # ---------- tray menu ----------

    def _build_menu(self) -> pystray.Menu:
        def gen(*_):
            with self._lock:
                items: list = []
                if not self.sessions:
                    items.append(pystray.MenuItem("No active sessions", None, enabled=False))
                else:
                    items.append(pystray.MenuItem("Sessions", None, enabled=False))
                    for s in sorted(self.sessions.values(), key=lambda x: -x.last_activity_at):
                        label = f"  {s.status:7} · {s.project_name} · {fmt_duration(s.duration())}"
                        items.append(pystray.MenuItem(
                            label,
                            self._make_open_action(s.cwd),
                            enabled=bool(s.cwd),
                        ))
                items.append(pystray.Menu.SEPARATOR)
                items.append(pystray.MenuItem("Open log folder", self._open_vibe_dir))
                items.append(pystray.MenuItem("Test toast", self._test_toast))
                items.append(pystray.MenuItem("Quit", self._quit))
                return items
        return pystray.Menu(gen)

    def _make_open_action(self, cwd: str):
        def action(icon, item):
            if cwd:
                uri = "vscode://file/" + cwd.replace("\\", "/")
                subprocess.Popen(["cmd", "/c", "start", "", uri], shell=False)
        return action

    def _open_vibe_dir(self, icon, item):
        subprocess.Popen(["explorer", str(VIBE_DIR)])

    def _test_toast(self, icon, item):
        self._show_toast(
            title="Vibe · test",
            body="Toast system is working.",
            cwd=str(Path.cwd()),
            kind="info",
        )

    def _quit(self, icon, item):
        self._stop.set()
        icon.stop()

    # ---------- event handling ----------

    def _get_session(self, sid: str) -> Session:
        s = self.sessions.get(sid)
        if not s:
            s = Session(session_id=sid)
            self.sessions[sid] = s
        return s

    def _handle_event(self, rec: dict) -> None:
        sid = rec.get("session_id") or "_anonymous"
        event = rec.get("event", "")
        cwd = rec.get("cwd", "")
        ts = rec.get("ts", time.time())

        with self._lock:
            s = self._get_session(sid)
            if cwd and not s.cwd:
                s.cwd = cwd
            s.last_activity_at = ts

            if event == "SessionStart":
                s.started_at = ts
                s.status = "idle"
            elif event == "UserPromptSubmit":
                s.prompt_started_at = ts
                s.status = "working"
                s.done_at = None
            elif event == "Notification":
                s.status = "asking"
                message = str(rec.get("extra", {}).get("message", "Claude needs your attention"))
                self._toast_asking(s, message)
            elif event in ("PreToolUse", "PostToolUse"):
                if s.status != "asking":
                    s.status = "working"
            elif event == "Stop":
                s.done_at = ts
                s.status = "done"
                self._toast_done(s)
            elif event == "SubagentStop":
                pass  # leave main session untouched
            elif event == "SessionEnd":
                s.status = "done"
                s.done_at = ts

            log(f"{event:20} sid={sid[:8]} status={s.status} cwd={s.project_name}")

        self._refresh_icon()

    def _toast_done(self, s: Session) -> None:
        duration = fmt_duration(s.duration())
        self._show_toast(
            title=f"Claude Code · {s.project_name}",
            body=f"Finished · {duration}",
            cwd=s.cwd,
            kind="done",
        )

    def _toast_asking(self, s: Session, message: str) -> None:
        self._show_toast(
            title=f"Claude Code · {s.project_name}",
            body=message,
            cwd=s.cwd,
            kind="asking",
            ttl=20.0,
        )

    def _show_toast(self, title: str, body: str, cwd: str, kind: str, ttl: float = 5.0) -> None:
        try:
            subprocess.Popen(
                [
                    str(PYTHONW), str(PILL_SCRIPT),
                    "--title", title,
                    "--body", body,
                    "--cwd", cwd,
                    "--kind", kind,
                    "--ttl", str(ttl),
                ],
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
        except Exception as e:
            log(f"pill failed: {e}")

    # ---------- periodic tasks ----------

    def _refresh_icon(self) -> None:
        with self._lock:
            active = [s for s in self.sessions.values() if s.status in ("working", "asking")]
            asking = any(s.status == "asking" for s in active)
            working = any(s.status == "working" for s in active)
            recent_done = [s for s in self.sessions.values()
                           if s.status == "done" and s.done_at and time.time() - s.done_at < 8]

            if asking:
                state, color = "asking", COLORS["asking"]
            elif working:
                state, color = "working", COLORS["working"]
            elif recent_done:
                state, color = "done", COLORS["done"]
            else:
                state, color = "idle", COLORS["idle"]

            badge = len(active) > 1
            tooltip = self._build_tooltip(state, active)

        self.icon.icon = make_icon(color, badge="dot" if badge else None)
        self.icon.title = tooltip
        self.icon.update_menu()

    def _build_tooltip(self, state: str, active: list[Session]) -> str:
        if not active:
            return f"Vibe · {state}"
        parts = [f"Vibe · {state}"]
        for s in sorted(active, key=lambda x: -x.last_activity_at)[:5]:
            parts.append(f"  {s.project_name} ({s.status}, {fmt_duration(s.duration())})")
        return "\n".join(parts)

    def _gc_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(1.0)
            now = time.time()
            changed = False
            with self._lock:
                for sid in list(self.sessions):
                    s = self.sessions[sid]
                    if s.status == "done" and s.done_at and now - s.done_at > DONE_LINGER:
                        del self.sessions[sid]
                        changed = True
            if changed:
                self._refresh_icon()

    def _tail_loop(self) -> None:
        LOG_PATH.touch(exist_ok=True)
        offset = LOG_PATH.stat().st_size  # start at end — don't replay old events
        while not self._stop.is_set():
            try:
                size = LOG_PATH.stat().st_size
                if size < offset:
                    # file rotated or truncated
                    offset = 0
                if size > offset:
                    with LOG_PATH.open("r", encoding="utf-8") as f:
                        f.seek(offset)
                        chunk = f.read()
                        offset = f.tell()
                    for line in chunk.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except Exception as e:
                            log(f"parse error: {e} line={line[:120]}")
                            continue
                        self._handle_event(rec)
            except Exception as e:
                log(f"tail error: {e}")
            time.sleep(POLL_INTERVAL)

    # ---------- entry ----------

    def run(self) -> None:
        log("tray starting")
        threading.Thread(target=self._tail_loop, daemon=True).start()
        threading.Thread(target=self._gc_loop, daemon=True).start()
        self.icon.run()
        log("tray stopped")


if __name__ == "__main__":
    VibeTray().run()
