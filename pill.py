"""
Vibe pill — a self-drawn slide-in notification window.

Polished version:
- rounded corners (Win32 SetWindowRgn)
- bottom TTL progress bar, color-coded by event kind
- clean typography, no chrome, click-to-focus

Usage:
    pythonw pill.py --title "..." --body "..." --cwd "..." --kind done [--ttl 5]
"""

from __future__ import annotations

import argparse
import ctypes
import subprocess
import sys
import tkinter as tk

# ---------- visual constants ----------

KIND_COLOR = {
    "done":    "#00d97e",
    "asking":  "#ffb800",
    "error":   "#ff3b30",
    "info":    "#00d9ff",
    "working": "#00d9ff",
}

BG          = "#17171d"
FG_TITLE    = "#eeeef2"
FG_BODY     = "#9a9aa4"
TRACK_BG    = "#2a2a33"   # progress bar track

W, H        = 380, 82
MARGIN_X    = 20          # distance from screen right edge
MARGIN_Y    = 54          # distance from screen bottom (above taskbar)
RADIUS      = 14          # corner radius
BAR_H       = 2           # ttl progress bar height

SLIDE_MS    = 220
FADE_MS     = 240
FRAME_MS    = 16          # ~60fps


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--body", default="")
    ap.add_argument("--cwd", default="")
    ap.add_argument("--kind", default="info", choices=list(KIND_COLOR))
    ap.add_argument("--ttl", type=float, default=5.0)
    return ap.parse_args()


def round_corners(hwnd: int, w: int, h: int, radius: int) -> None:
    """Apply a rounded-rect region to the window (Win32 only)."""
    gdi32 = ctypes.windll.gdi32
    user32 = ctypes.windll.user32
    # +1 because CreateRoundRectRgn is exclusive on the right/bottom edges
    rgn = gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, radius, radius)
    user32.SetWindowRgn(hwnd, rgn, True)


class Pill:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.accent = KIND_COLOR.get(args.kind, KIND_COLOR["info"])

        self.root = tk.Tk()
        self.root.withdraw()
        self.win = tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.0)
        self.win.configure(bg=BG)

        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        self.final_x = screen_w - W - MARGIN_X
        self.final_y = screen_h - H - MARGIN_Y
        self.start_y = screen_h
        self.win.geometry(f"{W}x{H}+{self.final_x}+{self.start_y}")

        self._build_ui()
        self._bind_clicks()

        # wait for window to be realized before applying region
        self.win.update_idletasks()
        round_corners(self.win.winfo_id(), W, H, RADIUS)

        # schedule animations
        self._slide_start_ms = 0
        self.win.after(0, self._slide_in_step, 0)
        self._ttl_ms = int(self.args.ttl * 1000)
        self._ttl_elapsed = 0
        self.win.after(SLIDE_MS + FRAME_MS, self._ttl_tick)

    # ---------- ui ----------

    def _build_ui(self) -> None:
        wrap = tk.Frame(self.win, bg=BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=(14, 10))

        tk.Label(
            wrap, text=self.args.title, bg=BG, fg=FG_TITLE,
            font=("Segoe UI Semibold", 11), anchor="w", justify="left",
        ).pack(fill="x")

        tk.Label(
            wrap, text=self.args.body, bg=BG, fg=FG_BODY,
            font=("Segoe UI", 9), anchor="w", justify="left",
            wraplength=W - 48,
        ).pack(fill="x", pady=(3, 0))

        # ttl progress bar — pinned to bottom edge
        self.bar_track = tk.Frame(self.win, bg=TRACK_BG, height=BAR_H)
        self.bar_track.place(x=0, y=H - BAR_H, width=W, height=BAR_H)
        self.bar_fill = tk.Frame(self.bar_track, bg=self.accent, height=BAR_H)
        self.bar_fill.place(x=0, y=0, width=W, height=BAR_H)

    def _bind_clicks(self) -> None:
        def on_click(_event=None):
            if self.args.cwd:
                uri = "vscode://file/" + self.args.cwd.replace("\\", "/")
                try:
                    subprocess.Popen(["cmd", "/c", "start", "", uri], shell=False)
                except Exception:
                    pass
            self._fade_out(0)

        def walk(w):
            w.bind("<Button-1>", on_click)
            for c in w.winfo_children():
                walk(c)
        walk(self.win)

    # ---------- animation ----------

    def _slide_in_step(self, elapsed: int) -> None:
        t = min(1.0, elapsed / SLIDE_MS)
        eased = 1 - (1 - t) ** 3                 # ease-out cubic
        y = int(self.start_y + (self.final_y - self.start_y) * eased)
        self.win.geometry(f"{W}x{H}+{self.final_x}+{y}")
        self.win.attributes("-alpha", 0.96 * eased)
        if t < 1.0:
            self.win.after(FRAME_MS, self._slide_in_step, elapsed + FRAME_MS)

    def _ttl_tick(self) -> None:
        self._ttl_elapsed += FRAME_MS
        remaining = max(0.0, 1.0 - self._ttl_elapsed / self._ttl_ms)
        new_w = max(0, int(W * remaining))
        self.bar_fill.place_configure(width=new_w)
        if remaining > 0:
            self.win.after(FRAME_MS, self._ttl_tick)
        else:
            self._fade_out(0)

    def _fade_out(self, elapsed: int) -> None:
        t = min(1.0, elapsed / FADE_MS)
        self.win.attributes("-alpha", max(0.0, 0.96 * (1 - t)))
        if t < 1.0:
            self.win.after(FRAME_MS, self._fade_out, elapsed + FRAME_MS)
        else:
            self.root.after(0, self.root.destroy)

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    try:
        Pill(parse_args()).run()
    except Exception as e:
        sys.stderr.write(f"pill error: {e}\n")
        sys.exit(1)
