@echo off
rem 開發版：編好伺服器和擴充，開一個 7780 伺服器視窗和一個遊戲視窗；關掉伺服器視窗就停
chcp 65001 >nul
cd /d "%~dp0rust"
cargo build -p rof-server -p rof-gdext || (pause & exit /b 1)
start "ROF 伺服器 7780" cargo run -q -p rof-server -- --port=7780
if "%GODOT%"=="" set "GODOT=D:\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe"
start "" "%GODOT%" --path "%~dp0."
