# =====================================================================
# routers/tts.py —— 预留：语音合成（待接入）
#   计划：POST /api/tts  请求体 { "text": "要念的话" }
#        返回音频流（audio/mpeg），前端播的时候同步调
#        Live2DStage 暴露的 setMouthOpen() 做口型。
#   接入时在 providers/ 下新建 tts.py，这里再实现路由。
# =====================================================================

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["tts"])

# @router.post("/tts")
# async def tts(body: TTSIn):
#     ...
