# =====================================================================
# routers/chat.py —— 聊天接口（已实现）
#   POST /api/chat
#     请求体：{ "message": "用户说的话", "history": [{role, text}, ...] }
#     响应  ：SSE 流式，每帧 data: {"text": "片段"}，结束帧 data: [DONE]
# =====================================================================

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..llm_settings import resolve_llm
from ..providers.deepseek import stream_chat

router = APIRouter(prefix="/api", tags=["chat"])


class ChatIn(BaseModel):
    # 用户这一轮的输入
    message: str = Field(..., min_length=1, description="用户说的话")
    # 之前的对话（由前端回传；后端不存会话，无状态）
    history: list[dict] = Field(default_factory=list)


@router.post("/chat")
async def chat(body: ChatIn, request: Request):
    # Key 只来自当前登录账号在「设置」里配置并激活的那套（见 llm_settings.py）
    llm = resolve_llm(request)
    # 前端的 role 是 'user' / 'ai'，转成模型要的 'user' / 'assistant'
    history = [
        ("assistant" if m.get("role") == "ai" else "user", m.get("text", ""))
        for m in body.history
        if m.get("text")                      # 跳过空消息，省 token
    ]

    async def event_stream():
        try:
            async for kind, piece in stream_chat(
                history,
                body.message,
                api_key=llm["api_key"],
                base_url=llm["base_url"],
                model=llm["model"],
            ):
                # kind: 'status' | 'thinking' | 'text'
                payload = json.dumps({"type": kind, "text": piece}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as exc:              # 出错也要让前端退出“打字中”
            payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # 关掉 Nginx 缓冲（部署时用得上）
        },
    )
