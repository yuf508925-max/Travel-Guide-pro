from pathlib import Path

# =====================================================================
# config.py —— 全局常量
#   Key / Base URL / 模型名全部由用户在右上角「设置」里自己填，
#   按账号存在 user_providers 表（见 server/routers/providers.py）。
#   这里只放不随用户变化的常量（跨域白名单、内置默认值、生成参数）。
# =====================================================================

# 允许跨域的前端地址（Vite dev server）
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# 用户没填 Base URL / 模型名时用的内置默认值
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# 生成参数（固定值，不对外开放）
TEMPERATURE = 0.7
MAX_TOKENS = 2048
# ---- 本地 GPT-SoVITS 语音服务 ----
# 先在本地跑 api_v2.py（默认 9880），这里的地址要和它一致
SOVITS_API_URL = "http://127.0.0.1:9880"
# 参考音频：3~10 秒干净人声（微调模型推理也必须带）
SOVITS_REF_AUDIO = str(
    Path(__file__).resolve().parent.parent / "models" / "Furina_GPT_SoVITS" / "ref.wav"
)
# 参考音频对应的文字（GPT-SoVITS 需要）
SOVITS_PROMPT_TEXT = ""
SOVITS_TEXT_LANG = "zh"
SOVITS_PROMPT_LANG = "zh"