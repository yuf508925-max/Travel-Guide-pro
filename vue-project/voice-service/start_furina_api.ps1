# 启动芙宁娜本地语音服务（项目内，带自动关闭）
#   · 关掉本窗口 / Ctrl+C / 进程被杀 → 语音服务自动结束
#   · Travel Guide 后端退出约 15 秒后 → 语音服务自动结束
# 说明：所有路径都基于本脚本所在目录，整个项目可以放在任意盘符/路径下。
$ErrorActionPreference = "Continue"

$here = $PSScriptRoot
if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $here

Write-Host "=== 芙宁娜本地语音服务 ===" -ForegroundColor Cyan
Write-Host "  目录: $here" -ForegroundColor Gray
Write-Host "  关掉本窗口、或后端退出，语音服务会自动关闭" -ForegroundColor Gray

$py = Join-Path $here ".venv-gsv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host ""
    Write-Host "找不到语音环境：$py" -ForegroundColor Red
    Write-Host "先按 README 第四节 3 创建 voice-service\.venv-gsv 并安装依赖。" -ForegroundColor Yellow
    Read-Host "按回车关闭"
    exit 1
}

# 把项目自带的 ffmpeg 放到 PATH 最前面（GPT-SoVITS 处理参考音频要用）
$env:PATH = (Join-Path $here "ffmpeg-bin") + ";" + $env:PATH

& $py voice_service.py

Write-Host ""
Write-Host "语音服务已退出。" -ForegroundColor Yellow
Read-Host "按回车关闭"
