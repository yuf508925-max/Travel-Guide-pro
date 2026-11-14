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

from . import usage as usage_log
from .config import CORS_ORIGINS, DEEPSEEK_MODEL
from .db import init_db
from .providers.deepseek import aclose
from .routers import (
    conversations,
    admin,
    auth,
    chat,
    feedback,
    live2d,
    map_settings,
    memory,
    music,
    notice,
    poster,
    providers,
    routes,
    trains,
    trip,
    tts,
    usage,
    vlog,
    weather,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时准备、关闭时清理"""
    init_db()      # 建表：users / sessions（已存在就跳过）
    yield
    await aclose()


app = FastAPI(title="芙芙之旅 API", version="0.1.0", lifespan=lifespan)


# 这些前缀不打点：后台自己的统计接口、健康检查、以及前端主动上报的两个入口
_SKIP_USAGE = ("/api/admin", "/api/health", "/api/usage", "/api/visit")


@app.middleware("http")
async def count_api_calls(request: Request, call_next):
    """把每次后端接口调用记一行 usage_events（按路径归类）。

    只统计成功的请求（2xx/3xx），失败的不算用户在用功能。
    打点出错绝不影响主请求。
    """
    response = await call_next(request)
    path = request.url.path

    if (
        path.startswith("/api/")
        and not path.startswith(_SKIP_USAGE)
        and response.status_code < 400
    ):
        try:
            usage_log.record(
                kind=usage_log.kind_of(path),
                detail=f"{request.method} {path}"[:80],
                token=request.cookies.get("fufu_session"),
            )
        except Exception:
            pass

    return response


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
app.include_router(usage.router)     # /api/visit         页面访问 / 高德调用打点
app.include_router(feedback.router)  # /api/feedback      用户给管理员留言

# 后台管理：整组接口都挂在 require_admin 上（相当于 addPathPatterns("/api/admin/**")）
app.include_router(admin.router)     # /api/admin/*       用户管理（仅管理员）
app.include_router(chat.router)      # POST /api/chat（SSE 流式对话）
app.include_router(conversations.router)
app.include_router(memory.router)  # /api/conversations 多对话 + 每个对话一份记忆
app.include_router(music.router)    # /api/music/*       上传的音乐（临时目录 + 会话隔离）
app.include_router(notice.router)  # /api/notices      公告（后台发布，前台看）
app.include_router(providers.router) # /api/providers     多套 Key / 多个模型 / 切换
app.include_router(routes.router)    # /api/routes        行程面板的搜索记录（按账号隔离）
app.include_router(map_settings.router)  # /api/map      管理员配的高德 Key（全局一份）
app.include_router(trains.router)    # /api/trains        动车班次（12306 余票）
app.include_router(live2d.router)    # /api/live2d/*      AI 控制：大模型挑表情/动作
app.include_router(vlog.router)      # /api/vlog/*        「观看 vlog」：B站旅行视频

# ---- 预留（文件里是空壳，实现后自动生效）----
app.include_router(poster.router)    # POST /api/poster/* 旅行一图流
app.include_router(tts.router)       # POST /api/tts      语音合成
app.include_router(trip.router)      # POST /api/trip/*   行程规划
app.include_router(weather.router)   # GET  /api/weather  天气/地图


@app.get("/api/health")
async def health():
    """自检用：浏览器打开 http://localhost:8000/api/health 看后端活没活"""
    return {"ok": True, "provider": "deepseek", "model": DEEPSEEK_MODEL}
