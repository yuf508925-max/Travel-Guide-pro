# =====================================================================
# config.py —— 全局配置：环境变量 + 模型常量
#   想改模型 / 换接口地址 / 调参数，只改这一个文件就够了
# =====================================================================

import os
from pathlib import Path

from dotenv import load_dotenv

# 无论从哪个目录启动 uvicorn，都只认 server/.env
# override=True 很关键：系统环境变量里如果也有一个 DEEPSEEK_API_KEY，
# dotenv 默认不会覆盖它，结果用的就是旧 Key —— 必须让 .env 优先。
load_dotenv(Path(__file__).parent / ".env", override=True)

# ------------------------------------------------------------------
# DeepSeek API Key（必需）
#   写在 server/.env 里：DEEPSEEK_API_KEY=sk-xxxxxx
# ------------------------------------------------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    raise RuntimeError(
        "未设置 DEEPSEEK_API_KEY。请在 server/.env 中写入：DEEPSEEK_API_KEY=sk-xxxxxx"
    )

# 接口地址。官方就是这个；如果走中转/代理，在 .env 里覆盖即可https://api.deepseek.com
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

# 模型名。接口若报 “model not found”，把这里（或 .env）改成 deepseek-chat
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")

# 生成参数
TEMPERATURE = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.7"))
MAX_TOKENS = int(os.getenv("DEEPSEEK_MAX_TOKENS", "2048"))

# 允许跨域的前端地址（Vite dev server）
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]
