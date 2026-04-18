# Vibe Island for Windows

A tiny floating-pill notifier for [Claude Code](https://docs.claude.com/en/docs/claude-code) sessions on Windows.
Know when your agent finishes, when it needs a permission, and which of your parallel sessions is doing what — without tabbing back into the terminal.

> **Scope:** built for personal use on Windows 11. Roughly 500 lines of Python. No Rust, no native binaries, no admin rights. All reversible via an uninstall script.

## What it does

- **Finish notification** — when Claude Code's `Stop` event fires, a dark rounded pill slides up from the bottom-right corner: project name, duration, click-to-open in VS Code. Auto-dismisses.
- **Permission heads-up** — when Claude pauses to ask for approval (`Notification` event), an amber pill shows the project + the prompt. Still need to switch to the terminal to type `y` — the pill is a visual flag, not the approval UI.
- **Multi-session tray** — a system-tray icon tracks every active Claude session (by `session_id`). Right-click to see a per-project list with live status (`working` / `asking` / `done`) and open any project directly.

## Requirements

- Windows 10/11
- Python 3.10+ with `pip` (Anaconda works)
- Claude Code CLI installed and working
- ~10 MB disk

## Install

```powershell
# 1. Clone
git clone https://github.com/yunningtang/Vibe-Island-for-Windows.git D:\Code\vibeisland
cd D:\Code\vibeisland

# 2. Install the one Python dependency (pystray for the tray icon)
python -m pip install pystray pillow

# 3. Point Claude Code's hooks at hook.py.
#    Edit ~/.claude/settings.json and add (or merge) the hooks block below.
#    Replace D:\Anaconda3\python.exe with your actual Python path and
#    D:\Code\vibeisland with wherever you cloned this.
```

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "D:\\Anaconda3\\python.exe D:\\Code\\vibeisland\\hook.py SessionStart", "timeout": 5 }] }
    ],
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "D:\\Anaconda3\\python.exe D:\\Code\\vibeisland\\hook.py UserPromptSubmit", "timeout": 5 }] }
    ],
    "Notification": [
      { "hooks": [{ "type": "command", "command": "D:\\Anaconda3\\python.exe D:\\Code\\vibeisland\\hook.py Notification", "timeout": 5 }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "D:\\Anaconda3\\python.exe D:\\Code\\vibeisland\\hook.py Stop", "timeout": 5 }] }
    ]
  }
}
```

Then start the tray once manually:

```powershell
Start-Process -FilePath "D:\Anaconda3\pythonw.exe" -ArgumentList "D:\Code\vibeisland\tray.py" -WindowStyle Hidden
```

### Auto-start on login

Drop a shortcut into the Startup folder:

```powershell
$lnk = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\VibeTray.lnk"
$wsh = New-Object -ComObject WScript.Shell
$s = $wsh.CreateShortcut($lnk)
$s.TargetPath = "D:\Anaconda3\pythonw.exe"
$s.Arguments = '"D:\Code\vibeisland\tray.py"'
$s.WorkingDirectory = "D:\Code\vibeisland"
$s.WindowStyle = 7
$s.Save()
```

## Architecture

```
Claude Code ──hook event──► hook.py ──append──► ~/.vibe/sessions.jsonl
                                                         │
                                                   (tail)│
                                                         ▼
                                                     tray.py  ──fork──► pill.py (slide-in window)
                                                         │
                                                  (tray icon + menu)
```

| File | Role |
|---|---|
| [`hook.py`](hook.py) | Invoked by Claude Code per hook event. Reads stdin JSON, appends a record to `~/.vibe/sessions.jsonl`. Exits in <100 ms. |
| [`tray.py`](tray.py) | Long-running tray app. Tails the jsonl, maintains per-session state, spawns `pill.py` on `Stop`/`Notification`. |
| [`pill.py`](pill.py) | Standalone Tk window. Rounded corners via Win32 `SetWindowRgn`, TTL progress bar, click-to-open-in-VS-Code. |
| [`uninstall.ps1`](uninstall.ps1) | Reverses every change: stops tray, removes auto-start + registry entries, restores settings.json backup. |

### State files (`~/.vibe/`)

- `sessions.jsonl` — append-only event log. One JSON record per hook event. Safe to tail/inspect.
- `tray.log` — tray runtime log.

## Uninstall

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\Code\vibeisland\uninstall.ps1
```

The installer makes a `settings.json.bak-<timestamp>` before editing — uninstall restores the most recent backup automatically.

## Known limits

- **Windows only.** Uses Win32 APIs (`SetWindowRgn`) and Windows path conventions. No macOS/Linux port planned.
- **The pill isn't an approval UI.** It flags when Claude needs input; you still type `y`/`n` in the terminal. Building real in-pill approval needs blocking hook stdout with `{"permissionDecision": "allow"}` and is out of scope for this project.
- **Settings hot-reload.** Editing `~/.claude/settings.json` only affects *new* Claude sessions. Restart the terminal after install.
- **Windows toast API was abandoned.** First version tried WinRT toasts — Windows silently disables unregistered AppIds. Self-drawn Tk window turned out simpler and more reliable.

## License

MIT
