param([string]$Only)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Continue'
$test = '\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\scripts\tests\integration_assembly.py'
$log = '\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\docs\reports\asm_report.json'
if ($Only) {
    D:\FastProgram\python\python.exe -u -X utf8 $test --only $Only *> $log
} else {
    D:\FastProgram\python\python.exe -u -X utf8 $test *> $log
}
Write-Output "exit=$LASTEXITCODE"
