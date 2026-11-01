@echo off
chcp 65001 >nul
title 背单词助手
cd /d %~dp0
backend\.venv\Scripts\python.exe launcher.py
if errorlevel 1 pause
