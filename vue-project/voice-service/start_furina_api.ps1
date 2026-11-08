# 启动芙宁娜本地语音服务（项目内，带自动关闭）
#   · 关掉本窗口 / Ctrl+C / 进程被杀 → 语音服务自动结束
#   · Travel Guide 后端退出约 15 秒后 → 语音服务自动结束
$ErrorActionPreference = "Continue"
Write-Host "=== 芙宁娜本地语音服务 ===" -ForegroundColor Cyan
Write-Host "  目录: D:\test\Travel Guide pro\Travel Guide pro\vue-project\voice-service" -ForegroundColor Gray
Write-Host "  关掉本窗口、或后端退出，语音服务会自动关闭" -ForegroundColor Gray
Write-Host ""

Set-Location "D:\test\Travel Guide pro\Travel Guide pro\vue-project\voice-service"
$env:PATH = "D:\test\Travel Guide pro\Travel Guide pro\vue-project\voice-service\ffmpeg-bin;$env:PATH"
& ".\\.venv-gsv\Scripts\python.exe" voice_service.py

Write-Host ""
Write-Host "语音服务已退出。" -ForegroundColor Yellow
Read-Host "按回车关闭"
