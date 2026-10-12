param([string]$Only)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Continue'
$test = '\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\scripts\tests\integration_sw2018.py'
D:\FastProgram\python\python.exe -u -X utf8 "$test" --only $Only 2>&1 | Tee-Object -FilePath '\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\docs\reports\one_report.txt'
Write-Output "exit=$LASTEXITCODE"
