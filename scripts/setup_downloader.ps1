# Copy bộ tải video (yt-dlp, cookies, bgutil PO token) vào thư mục dữ liệu của app.
# Dùng:  powershell -ExecutionPolicy Bypass -File scripts\setup_downloader.ps1 [-Source "E:\TAI VIDEO MOI NHAT - BAO GOM SUB"]
param([string]$Source = "E:\TAI VIDEO MOI NHAT - BAO GOM SUB")

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RootDir ".venv\Scripts\python.exe"
$Data = & $Python -c "from app.config import AppPaths; print(AppPaths.create().root)"
$Tools = Join-Path $Data "tools"
New-Item -ItemType Directory -Force $Tools | Out-Null

foreach ($f in "yt-dlp.exe", "cookies.txt") {
    Copy-Item -LiteralPath (Join-Path $Source $f) -Destination $Tools -Force
}
$Pot = Join-Path $Source "bgutil-ytdlp-pot-provider"
Copy-Item -LiteralPath $Pot -Destination $Tools -Recurse -Force
Write-Host "Đã cài bộ tải vào $Tools"
Write-Host "Cần FFmpeg (C:\ffmpeg\bin) và Node.js trong PATH. Đổi thư mục lưu trong settings.json mục 'download'."
