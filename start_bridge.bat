@echo off
rem Bridge MCP cho Profile YTB: chi nghe tren IP NetBird cua PC.
rem Dat file nay CUNG THU MUC voi mcp_server.py roi bam dup de chay. Giu cua so mo.
cd /d "%~dp0"
set NB_IP=100.83.225.209
set PORT=8765

python -m pip install --quiet mcp-proxy
if errorlevel 1 (
  echo [LOI] Khong cai duoc mcp-proxy. Kiem tra Python va Internet.
  pause
  exit /b 1
)

echo Bridge dang chay tai http://%NB_IP%:%PORT%/sse
where mcp-proxy >nul 2>&1
if %errorlevel%==0 (
  mcp-proxy --host %NB_IP% --port %PORT% --pass-environment -- python mcp_server.py
) else (
  python -m mcp_proxy --host %NB_IP% --port %PORT% --pass-environment -- python mcp_server.py
)
echo.
echo Bridge da dung. Xem thong bao loi o tren.
pause
