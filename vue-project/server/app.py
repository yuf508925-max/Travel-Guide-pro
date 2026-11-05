# =====================================================================
# app.py —— FastAPI 入口
#   只做三件事：装中间件、挂路由、管理生命周期
#   具体逻辑都在 routers/ 和 providers/ 里
#
#   启动（在 vue-project 目录下执行，不要 cd 进 server）：
#     uvicorn server.app:app --port 8000 --reload
# =====================================================================

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import CORS_ORIGINS, DEEPSEEK_MODEL
from .db import init_db
from .providers.deepseek import aclose
from .routers import auth, chat, poster, trip, tts, weather


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时准备、关闭时清理"""
    init_db()      # 建表：users / sessions（已存在就跳过）
    yield
    await aclose()


app = FastAPI(title="芙芙之旅 API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """去掉 422 错误里默认回显的 input（可能包含用户刚输入的密码）"""
    errors = [
        {k: v for k, v in err.items() if k != "input"} for err in exc.errors()
    ]
    return JSONResponse(status_code=422, content=jsonable_encoder({"detail": errors}))

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 已实现 ----
app.include_router(auth.router)      # /api/auth/*        注册 / 登录 / 登出 / 当前用户
app.include_router(chat.router)      # POST /api/chat（SSE 流式对话）

# ---- 预留（文件里是空壳，实现后自动生效）----
app.include_router(poster.router)    # POST /api/poster/* 旅行一图流
app.include_router(tts.router)       # POST /api/tts      语音合成
app.include_router(trip.router)      # POST /api/trip/*   行程规划
app.include_router(weather.router)   # GET  /api/weather  天气/地图


@app.get("/api/health")
async def health():
    """自检用：浏览器打开 http://localhost:8000/api/health 看后端活没活"""
    return {"ok": True, "provider": "deepseek", "model": DEEPSEEK_MODEL}
