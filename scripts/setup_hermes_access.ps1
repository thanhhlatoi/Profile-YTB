# Cho Hermes Agent (VPS hoặc máy khác) điều khiển Profile YTB trên Windows qua SSH.
# Dùng:  powershell -ExecutionPolicy Bypass -File scripts\setup_hermes_access.ps1 C:\duong\dan\hermes.pub
# Khóa này CHỈ chạy được MCP server của Profile YTB: không mở được shell, không forward cổng.
# Cần quyền Administrator (để cài OpenSSH Server); script tự hỏi nâng quyền.
param([Parameter(Position = 0)][string]$KeyFile)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot

if (-not $KeyFile -or -not (Test-Path -LiteralPath $KeyFile -PathType Leaf)) {
    Write-Host "Dùng: setup_hermes_access.ps1 <file khóa công khai .pub của máy chạy Hermes>"
    exit 2
}
$KeyFile = (Resolve-Path -LiteralPath $KeyFile).Path
$Key = (Get-Content -LiteralPath $KeyFile -TotalCount 1).Trim()
if ($Key -notmatch '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-)') {
    Write-Host "File $KeyFile không phải khóa công khai SSH."
    exit 2
}
$Python = Join-Path $RootDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host "Chưa có .venv. Chạy trước:  python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

$Principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Cần quyền Administrator, đang mở cửa sổ nâng quyền..."
    $Process = Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit",
        "-File", "`"$PSCommandPath`"", "`"$KeyFile`""
    )
    exit $Process.ExitCode
}

# 1. OpenSSH Server
$Capability = Get-WindowsCapability -Online -Name "OpenSSH.Server*" | Select-Object -First 1
if ($Capability.State -ne "Installed") {
    Write-Host "Đang cài OpenSSH Server (vài phút)..."
    Add-WindowsCapability -Online -Name $Capability.Name | Out-Null
}
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd
if (-not (Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" `
        -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
}

# 2. Wrapper chạy MCP server (đường dẫn không có dấu cách để dùng trong authorized_keys)
$WrapperDir = Join-Path $env:LOCALAPPDATA "profile-ytb"
New-Item -ItemType Directory -Force -Path $WrapperDir | Out-Null
$Wrapper = Join-Path $WrapperDir "profile-ytb-mcp.cmd"
if ($Wrapper -match '\s') {
    Write-Host "Đường dẫn $Wrapper có dấu cách, OpenSSH không chạy được. Hãy dùng user không dấu cách."
    exit 1
}
$Utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($Wrapper, "@echo off`r`ncd /d `"$RootDir`"`r`n`"$Python`" -m app.mcp_server`r`n", $Utf8)

# 3. Thêm khóa, giới hạn chỉ chạy MCP. User thuộc nhóm Administrators dùng file chung của sshd.
$IsAdminUser = (whoami /groups) -match "S-1-5-32-544"
if ($IsAdminUser) {
    $AuthorizedKeys = Join-Path $env:ProgramData "ssh\administrators_authorized_keys"
} else {
    $AuthorizedKeys = Join-Path $env:USERPROFILE ".ssh\authorized_keys"
    New-Item -ItemType Directory -Force -Path (Split-Path $AuthorizedKeys) | Out-Null
}
if (-not (Test-Path -LiteralPath $AuthorizedKeys)) { [IO.File]::WriteAllText($AuthorizedKeys, "", $Utf8) }
$KeyBody = ($Key -split '\s+')[1]
if ((Get-Content -LiteralPath $AuthorizedKeys -Raw) -match [regex]::Escape($KeyBody)) {
    Write-Host "Khóa này đã có trong $AuthorizedKeys, giữ nguyên."
} else {
    [IO.File]::AppendAllText($AuthorizedKeys, "command=`"$Wrapper`",restrict $Key`n", $Utf8)
    Write-Host "Đã thêm khóa (chỉ được chạy MCP) vào $AuthorizedKeys"
}
if ($IsAdminUser) {
    # sshd bỏ qua file này nếu người khác ngoài Administrators/SYSTEM sửa được.
    icacls $AuthorizedKeys /inheritance:r /grant "*S-1-5-32-544:F" /grant "*S-1-5-18:F" | Out-Null
}

# 4. In cấu hình cho Hermes
$Tailscale = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $Tailscale -and (Test-Path "$env:ProgramFiles\Tailscale\tailscale.exe")) {
    $Tailscale = Get-Command "$env:ProgramFiles\Tailscale\tailscale.exe"
}
$Ip = $null
$Network = "Tailscale"
if ($Tailscale) { $Ip = (& $Tailscale.Source ip -4 2>$null | Select-Object -First 1) }
if (-not $Ip) {
    $NetBird = Get-Command netbird -ErrorAction SilentlyContinue
    if (-not $NetBird -and (Test-Path "$env:ProgramFiles\NetBird\netbird.exe")) {
        $NetBird = Get-Command "$env:ProgramFiles\NetBird\netbird.exe"
    }
    if ($NetBird) {
        # "NetBird IP: 100.92.1.2/16"
        $Line = (& $NetBird.Source status 2>$null) | Select-String -Pattern 'NetBird IP:\s*([\d.]+)'
        if ($Line) { $Ip = $Line.Matches[0].Groups[1].Value; $Network = "NetBird" }
    }
}
if (-not $Ip) {
    $Network = "mạng LAN"
    $Ip = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.PrefixOrigin -in "Dhcp", "Manual" -and $_.IPAddress -notlike "169.254*" } |
        Select-Object -First 1).IPAddress
}

Write-Host @"

Xong. Dán đoạn sau vào ~/.hermes/config.yaml trên máy chạy Hermes
(đổi đường dẫn khóa riêng nếu bạn đặt tên khác):

mcp_servers:
  profile_ytb:
    command: "ssh"
    args: ["-T", "-i", "~/.ssh/hermes_profile_ytb", "-o", "BatchMode=yes",
           "-o", "ServerAliveInterval=30", "$env:USERNAME@$Ip"]
    timeout: 300
    connect_timeout: 60

Lưu ý:
- IP trên lấy từ $Network ($Ip). Hermes chạy trên VPS thì cần Tailscale hoặc NetBird trên cả 2 máy.
- App Profile YTB phải đang chạy (dưới khay). Bật tự chạy: scripts\install_autostart.ps1
"@
