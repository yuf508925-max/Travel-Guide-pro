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

from ..db import db
from .. import agent_tools, usage
from ..llm_settings import resolve_llm
from ..providers.deepseek import stream_chat

router = APIRouter(prefix="/api", tags=["chat"])


class ChatIn(BaseModel):
    # 用户这一轮的输入
    message: str = Field(..., min_length=1, description="用户说的话")
    # 之前的对话（由前端回传；后端只存「摘要记忆」，不存全文）
    history: list[dict] = Field(default_factory=list)
    # 当前所在对话（可空：老版本前端不传就是无记忆模式）
    conversation_id: int | None = None


@router.post("/chat")
async def chat(body: ChatIn, request: Request):
    # Key 只来自当前登录账号在「设置」里配置并激活的那套（见 llm_settings.py）
    llm = resolve_llm(request)

    # 记一行「这套 Key + 这个模型」的调用，后台用它画每个 Key 的用量曲线
    if llm.get("provider_id"):
        usage.record(
            kind="chat_key",
            detail=f"{llm['provider_id']}|{llm['model']}",
            token=request.cookies.get("fufu_session"),
        )
    # 取这个对话之前存下的摘要，作为这一轮的长期记忆
    memory = ""
    user_id = llm.get("user_id")
    if body.conversation_id and user_id:
        with db() as conn:
            row = conn.execute(
                "SELECT summary FROM conversations WHERE id = ? AND user_id = ?",
                (body.conversation_id, user_id),
            ).fetchone()
            if row:
                memory = row["summary"] or ""
                conn.execute(
                    "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                    (body.conversation_id,),
                )

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
                memory=memory,
                # 天气 / 火车 / 路线三个工具（见 server/agent_tools.py）
                tools=agent_tools.TOOLS,
                tool_executor=agent_tools.execute,
            ):
                # kind: 'status' | 'thinking' | 'text' | 'tool'
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
