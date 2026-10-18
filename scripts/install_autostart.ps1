# Tự chạy app (ẩn xuống khay) khi đăng nhập Windows.
# Dùng:  powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 [-Remove]
param([switch]$Remove)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
$Target = Join-Path ([Environment]::GetFolderPath("Startup")) "Chrome Profile Manager.lnk"

if ($Remove) {
    Remove-Item -LiteralPath $Target -ErrorAction SilentlyContinue
    Write-Host "Đã tắt tự khởi động."
    exit 0
}

$Pythonw = Join-Path $RootDir ".venv\Scripts\pythonw.exe"
if (-not (Test-Path -LiteralPath $Pythonw)) {
    Write-Host "Chưa có .venv. Chạy trước:  python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}
$Shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($Target)
$Shortcut.TargetPath = $Pythonw
$Shortcut.Arguments = "-m app.main --minimized"
$Shortcut.WorkingDirectory = $RootDir
$Shortcut.Description = "Chạy lịch tác vụ Chrome profile"
$Shortcut.Save()
Write-Host "Đã bật tự khởi động: $Target"
