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

# ---- 高德地图 JS API（行程用，写死一份，不再让用户填） ----
# 说明：这是「Web端 (JS API)」类型的 Key，它本来就要写进浏览器脚本地址里，
#       任何人打开页面都能看到，属于公开标识而不是机密凭据（真正的保护靠
#       安全密钥 + 高德控制台里配置域名白名单）。所以直接放在代码里没问题。
# 换 Key 只改这里，前端不用动。
AMAP_JS_KEY = "ad13ee3ce44bbc652ff1a9c7956c6312"
AMAP_SECURITY_CODE = "29e9e182bdd83171781095f6192df387"
# ---- 本地 GPT-SoVITS 语音服务 ----
# 先在本地跑 api_v2.py（默认 9880），这里的地址要和它一致
SOVITS_API_URL = "http://127.0.0.1:9880"
# 参考音频：3~10 秒干净人声（微调模型推理也必须带）
SOVITS_REF_AUDIO = str(
    Path(__file__).resolve().parent.parent / "models" / "Furina_GPT_SoVITS" / "ref.wav"
)
# 参考音频对应的文字（GPT-SoVITS 需要）
SOVITS_PROMPT_TEXT = "富有的、贫穷的，带着酒杯或一无所有的子民们，举起酒杯吧！"
# 是否把上面这句作为"参考文本"发给 GPT-SoVITS。
# 实测当前 ref.wav 和这句话对不上：带上它模型会把这句话也念出来（2 秒变 7~8 秒）。
# 换成与这句话对应的参考音频后，把它改成 True 即可。
SOVITS_USE_PROMPT_TEXT = True
SOVITS_TEXT_LANG = "zh"
SOVITS_PROMPT_LANG = "zh"