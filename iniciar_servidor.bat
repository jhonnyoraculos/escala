@echo off
setlocal

cd /d "%~dp0"

set PORT=5000
set HOST_IP=

for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$ips = Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Dhcp,Manual | Where-Object { $_.IPAddress -notlike '169.254*' -and $_.IPAddress -ne '127.0.0.1' } | Select-Object -First 1 -ExpandProperty IPAddress; if ($ips) { $ips }"`) do set HOST_IP=%%i

echo.
echo Servidor local: http://localhost:%PORT%/carregamentos
if defined HOST_IP (
  echo Servidor na rede: http://%HOST_IP%:%PORT%/carregamentos
) else (
  echo IP nao detectado. Rode "ipconfig" para ver o IPv4.
)
echo.

python -m flask --app web.app run --host=0.0.0.0 --port=%PORT%

pause
