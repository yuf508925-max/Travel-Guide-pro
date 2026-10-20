# =====================================================================
# app.py —— FastAPI 入口
#   只做三件事：装中间件、挂路由、管理生命周期
#   具体逻辑都在 routers/ 和 providers/ 里
#
#   启动（在 vue-project 目录下执行，不要 cd 进 server）：
#     uvicorn server.app:app --port 8000 --reload
# =====================================================================

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS, DEEPSEEK_MODEL
from .providers.deepseek import aclose
from .routers import chat, trip, tts, weather


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时准备、关闭时清理（目前只需要关掉 AI 客户端的连接）"""
    yield
    await aclose()


app = FastAPI(title="芙芙之旅 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 已实现 ----
app.include_router(chat.router)      # POST /api/chat（SSE 流式对话）

# ---- 预留（文件里是空壳，实现后自动生效）----
app.include_router(tts.router)       # POST /api/tts      语音合成
app.include_router(trip.router)      # POST /api/trip/*   行程规划
app.include_router(weather.router)   # GET  /api/weather  天气/地图


@app.get("/api/health")
async def health():
    """自检用：浏览器打开 http://localhost:8000/api/health 看后端活没活"""
    return {"ok": True, "provider": "deepseek", "model": DEEPSEEK_MODEL}
