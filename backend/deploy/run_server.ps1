# -*- coding: utf-8 -*-
"""本地启动后端（Windows PowerShell）。

用法：
    powershell -ExecutionPolicy Bypass -File deploy\run_server.ps1
    powershell -ExecutionPolicy Bypass -File deploy\run_server.ps1 -Port 8010 -ApiKey "my-key"
"""
param(
    [int]$Port = 8000,
    [string]$ApiKey = "",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($ApiKey) { $env:STEELSCAN_API_KEY = $ApiKey }
Write-Host "服务目录: $root"
Write-Host "端口: $Port"
if ($env:STEELSCAN_API_KEY) { Write-Host "API Key: 已启用（请求头 X-API-Key）" } else { Write-Host "API Key: 未启用（仅本机/内网使用）" }
Write-Host "启动: $Python server.py --host 0.0.0.0 --port $Port"
& $Python server.py --host 0.0.0.0 --port $Port
