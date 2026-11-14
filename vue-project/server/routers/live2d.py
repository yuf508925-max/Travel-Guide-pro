# =====================================================================
# routers/live2d.py —— AI 控制 Live2D
#   GET  /api/live2d/catalog  当前允许的动作/表情清单（调试用，也方便前端对照）
#   POST /api/live2d/act      「芙芙刚说了这句话，她现在该摆什么表情？」
#
# 只在「AI 控制」模式开启时被前端调用，一轮回复调一次。
# 挑表情本身失败（没配 Key、模型抽风）不算错误：返回空动作，前端保持现状，
# 聊天该怎么聊还怎么聊——不能因为一个表情把整段对话搞崩。
# =====================================================================

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..llm_settings import resolve_llm
from ..providers.deepseek import LIVE2D_EXPRESSIONS, LIVE2D_MOTIONS, choose_live2d_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live2d", tags=["live2d"])


class HistoryItem(BaseModel):
    """一条对话上下文：role = user / ai"""
    role: str = Field(default="user", max_length=16)
    text: str = Field(default="", max_length=2000)


class ActIn(BaseModel):
    # 芙芙这一轮的回复（通话模式下是完整那段）；挂机时没有，为空
    reply: str = Field(default="", max_length=2000)
    # 用户这轮说了什么，给模型当上下文，可以没有
    user: str = Field(default="", max_length=1000)
    # 当前对话最近几条消息——只会是前端正在看的那条对话，不跨对话
    history: list[HistoryItem] = Field(default_factory=list, max_length=16)
    # true = 挂机被动触发（她没有新台词），让模型按上下文挑个自发小表情
    idle: bool = False
    # 这条对话上一轮演过的动作/表情，避免连着两轮挑同一个
    previous: dict | None = None


@router.get("/catalog")
async def catalog():
    return {
        "motions": list(LIVE2D_MOTIONS),
        "expressions": LIVE2D_EXPRESSIONS,
    }


@router.post("/act")
async def act(body: ActIn, request: Request):
    llm = resolve_llm(request)
    try:
        return await choose_live2d_action(
            reply=body.reply,
            user_text=body.user,
            history=[item.model_dump() for item in body.history],
            idle=body.idle,
            previous=body.previous,
            api_key=llm["api_key"],
            base_url=llm["base_url"],
            model=llm["model"],
        )
    except Exception as exc:
        # 没配 Key / 接口挂了 / 超时：静默降级，前端什么都不切
        logger.warning("[live2d] 挑表情失败：%s", exc)
        return {"motion": None, "expression": None, "reason": "", "error": str(exc)}
