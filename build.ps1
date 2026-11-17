# encoding: utf-8-sig
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location -Path $PSScriptRoot

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "       VoxLocal 自动化构建脚本" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

$PYTHON = "c:\code\voxlocal\.venv\Scripts\python.exe"

Write-Host "[1/3] 正在检查并安装必要的依赖..." -ForegroundColor Yellow
if (Test-Path "requirements.txt") {
    & $PYTHON -m pip install -r requirements.txt -q
}
& $PYTHON -m pip install pyinstaller -q

Write-Host "`n[2/3] 正在清理历史构建产物..." -ForegroundColor Yellow
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
Get-ChildItem -Path . -Filter "*.spec" | Remove-Item -Force

Write-Host "`n[3/3] 正在执行 Python 打包流程..." -ForegroundColor Yellow
& $PYTHON build.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n=========================================" -ForegroundColor Red
    Write-Host "❌ 打包失败！请检查上述日志排查错误。" -ForegroundColor Red
    Write-Host "=========================================" -ForegroundColor Red
} else {
    Write-Host "`n=========================================" -ForegroundColor Green
    Write-Host "✅ 打包完成！EXE 位于 dist\VoxLocal\ 目录" -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Green
}

Read-Host -Prompt "按 Enter 键退出"
