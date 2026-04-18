# Vibe uninstaller — reverses every change installed by this project.
# Run:  powershell -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1
# Re-running is safe (idempotent).

$ErrorActionPreference = "Continue"
Write-Host "--- Vibe uninstall ---" -ForegroundColor Cyan

# 1. Stop the running tray
Get-CimInstance Win32_Process | Where-Object {
  $_.Name -eq "pythonw.exe" -and $_.CommandLine -like "*tray.py*"
} | ForEach-Object {
  Write-Host "Stopping tray (PID $($_.ProcessId))"
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

# 2. Remove auto-start shortcut
$startup = Join-Path ([Environment]::GetFolderPath("Startup")) "VibeTray.lnk"
if (Test-Path $startup) {
  Remove-Item $startup -Force
  Write-Host "Removed $startup"
}

# 3. Remove Start Menu shortcut (was for toast AUMID, now unused)
$startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "Claude Code Vibe.lnk"
if (Test-Path $startMenu) {
  Remove-Item $startMenu -Force
  Write-Host "Removed $startMenu"
}

# 4. Remove registry entries
$regPaths = @(
  "HKCU:\Software\Classes\AppUserModelId\ClaudeCode.Vibe",
  "HKCU:\Software\Microsoft\Windows\CurrentVersion\Notifications\Settings\ClaudeCode.Vibe"
)
foreach ($p in $regPaths) {
  if (Test-Path $p) {
    Remove-Item -Path $p -Recurse -Force
    Write-Host "Removed registry: $p"
  }
}

# 5. Restore settings.json backup if present, else just warn
$settings = Join-Path $env:USERPROFILE ".claude\settings.json"
$backup = Get-ChildItem -Path (Split-Path $settings) -Filter "settings.json.bak-*" -ErrorAction SilentlyContinue |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($backup) {
  Copy-Item $backup.FullName $settings -Force
  Write-Host "Restored settings.json from $($backup.Name)"
} else {
  Write-Host "WARNING: no settings.json backup found — edit ~/.claude/settings.json manually if needed" -ForegroundColor Yellow
}

# 6. Offer to delete the event log directory
$vibe = Join-Path $env:USERPROFILE ".vibe"
if (Test-Path $vibe) {
  $ans = Read-Host "Delete $vibe (event log + tray log)? [y/N]"
  if ($ans -match "^[Yy]") {
    Remove-Item $vibe -Recurse -Force
    Write-Host "Removed $vibe"
  } else {
    Write-Host "Left $vibe in place"
  }
}

# 7. Offer to uninstall pystray
$ans = Read-Host "Uninstall the pystray pip package from D:\Anaconda3? [y/N]"
if ($ans -match "^[Yy]") {
  & "D:\Anaconda3\python.exe" -m pip uninstall -y pystray
}

Write-Host ""
Write-Host "Done. The source folder D:\Code\vibeisland is left in place — delete it manually if you want." -ForegroundColor Green
