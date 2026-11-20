@echo off
setlocal enabledelayedexpansion
title AirTrack Launcher
cls

echo ============================================================
echo                      AIRTRACK LAUNCHER
echo ============================================================
echo.
echo  [1] Normal Wi-Fi Mode  (Home / College / Office)
echo      - Both laptop and phone are on the same Wi-Fi.
echo      - No administrator rights needed.
echo.
echo  [2] Offline Hotspot Mode (Cafes / Travel / No Wi-Fi)
echo      - Laptop creates its own offline Wi-Fi network.
echo      - Zero cellular data used on phone.
echo.
echo ============================================================
set /p mode="Select Mode [1 or 2] (Default is 1): "
if "%mode%"=="" set mode=1

if "%mode%"=="1" (
    cls
    echo ============================================================
    echo           STARTING AIRTRACK IN NORMAL WI-FI MODE
    echo ============================================================
    python trackpad.py
    pause
    exit /b
)

if "%mode%"=="2" (
    :: Elevate to Administrator for hotspot configuration
    net session >nul 2>&1
    if %errorLevel% neq 0 (
        echo Requesting Administrator privileges to start Hotspot...
        powershell -Command "Start-Process '%~f0' -Verb RunAs"
        exit /b
    )

    cls
    echo ============================================================
    echo           STARTING AIRTRACK OFFLINE HOTSPOT
    echo ============================================================
    netsh wlan set hostednetwork mode=allow ssid=AirTrack key=12345678 >nul
    netsh wlan start hostednetwork
    echo.
    echo  [+] Wi-Fi Network Name : AirTrack
    echo  [+] Wi-Fi Password     : 12345678
    echo  [+] Fixed iPhone URL   : http://192.168.137.1:5000
    echo.
    echo ============================================================
    python trackpad.py
    netsh wlan stop hostednetwork >nul
    exit /b
)