# =====================================================================
# routers/usage.py —— 前端主动上报的两类打点
#   POST /api/visit        页面访问（App 挂载时打一次）
#   POST /api/usage/amap   高德地图调用（地图初始化 / 搜索 / 路线规划）
# 后端自己的接口调用量由 app.py 的中间件自动记，不需要前端参与。
# =====================================================================

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from .. import usage
from .auth import optional_user

router = APIRouter(prefix="/api", tags=["usage"])


class AmapEvent(BaseModel):
    # transfer / driving / walking / place-search / geocode / map-init
    action: str = Field(min_length=1, max_length=40)


def _token(request: Request) -> str | None:
    return request.cookies.get("fufu_session")


@router.post("/visit")
def visit(request: Request):
    """页面访问：只记登录用户；没登录 / token 失效就整条不记（usage_events.user_id 不允许为空）。"""
    user = optional_user(request)
    usage.record(
        kind="visit",
        detail=request.headers.get("referer", "")[:80],
        user_id=user["id"] if user else None,
        token=_token(request),
    )
    return {"ok": True}


@router.post("/usage/amap")
def amap_usage(body: AmapEvent, request: Request):
    """高德 JS API 每次真正发请求时，前端来报一次（浏览器的请求不经过我们后端）。"""
    user = optional_user(request)
    usage.record(
        kind="amap",
        detail=body.action,
        user_id=user["id"] if user else None,
        token=_token(request),
    )
    return {"ok": True}
