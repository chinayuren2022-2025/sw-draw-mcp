[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Continue'
# 从 WSL 调用本脚本：pwsh.exe -NoProfile -ExecutionPolicy Bypass -File '<本文件 UNC 路径>'
D:\FastProgram\python\python.exe -X utf8 '\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\bridge\sw_bridge_probe.py'
