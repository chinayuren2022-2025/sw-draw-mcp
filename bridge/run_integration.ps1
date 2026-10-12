[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Continue'
$test = '\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\scripts\tests\integration_sw2018.py'
$log = '\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\docs\reports\integration_report.json'
D:\FastProgram\python\python.exe -u -X utf8 "$test" *> "$log"
Write-Output "exit=$LASTEXITCODE"
