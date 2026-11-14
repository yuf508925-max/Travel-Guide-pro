# =====================================================================
# routers/conversations.py —— 「多个对话 + 每个对话一份记忆」
# ---------------------------------------------------------------------
#   表：conversations(id, user_id, title, summary, created_at, updated_at)
#   · 只存「摘要」，不存聊天全文；全文只活在前端，关网页时压成 summary
#   · summary 只对这一条对话生效，换对话就换一套记忆
#
#   接口：
#     GET    /api/conversations                 列出我的对话
#     POST   /api/conversations                 新建（可带标题）
#     PATCH  /api/conversations/{id}            改名
#     DELETE /api/conversations/{id}            删除
#     POST   /api/conversations/{id}/summarize  关网页时把整段对话压成摘要
# =====================================================================

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import db
from .auth import optional_user
from ..llm_settings import resolve_llm
from ..providers.deepseek import summarize_chat

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

MAX_TITLE = 40


def _me(request: Request) -> dict:
    user = optional_user(request)
    if user is None:
        raise HTTPException(401, "请先登录")
    return user


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "summary": row["summary"] or "",
        "summarized_upto": row["summarized_upto"] or 0,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _owned(conn, conversation_id: int, user_id: int):
    row = conn.execute(
        "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
        (conversation_id, user_id),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "对话不存在")
    return row


class ConversationIn(BaseModel):
    title: str = Field("", max_length=MAX_TITLE)


class RenameIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=MAX_TITLE)


class SummarizeIn(BaseModel):
    # 前端把「还没总结过的那一段」发上来：[{role: 'user'|'ai', text: '...'}]
    # 每到 10 条总结一次，退网页时把剩下的也总结掉
    messages: list[dict] = Field(default_factory=list)


@router.get("")
def list_conversations(request: Request):
    user = _me(request)
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, title, summary, summarized_upto, created_at, updated_at
              FROM conversations
             WHERE user_id = ?
             ORDER BY updated_at DESC, id DESC
             LIMIT 100
            """,
            (user["id"],),
        ).fetchall()
    return {"conversations": [_row_to_dict(r) for r in rows]}


@router.post("")
def create_conversation(body: ConversationIn, request: Request):
    user = _me(request)
    title = body.title.strip()[:MAX_TITLE] or "新的对话"
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (user_id, title) VALUES (?, ?)",
            (user["id"], title),
        )
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row_to_dict(row)


@router.patch("/{conversation_id}")
def rename_conversation(conversation_id: int, body: RenameIn, request: Request):
    user = _me(request)
    title = body.title.strip()[:MAX_TITLE]
    if not title:
        raise HTTPException(400, "标题不能为空")
    with db() as conn:
        _owned(conn, conversation_id, user["id"])
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = datetime('now') WHERE id = ?",
            (title, conversation_id),
        )
        row = _owned(conn, conversation_id, user["id"])
    return _row_to_dict(row)


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: int, request: Request):
    user = _me(request)
    with db() as conn:
        _owned(conn, conversation_id, user["id"])
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    return {"ok": True}


@router.post("/{conversation_id}/summarize")
async def summarize_conversation(
    conversation_id: int, body: SummarizeIn, request: Request
):
    """把这批消息并进这段对话的记忆（每 10 条 / 离开页面时调）

    · 太短（不足 2 行有效发言）跳过，省一次模型调用
    · 返回本次新增的记忆条目，前端可以就地提示
    """
    user = _me(request)
    with db() as conn:
        row = _owned(conn, conversation_id, user["id"])
        previous = (row["summary"] or "").strip()

    lines = []
    for m in body.messages:
        text = str(m.get("text") or "").strip()
        if not text:
            continue
        who = "用户" if m.get("role") == "user" else "芙宁娜"
        lines.append(f"{who}：{text}")

    if len(lines) < 2:
        return {"summary": previous, "added": [], "skipped": "对话太短，不用记"}

    transcript = "\n".join(lines)
    llm = resolve_llm(request)
    if not llm.get("api_key"):
        return {"summary": previous, "added": [], "skipped": "没有可用的 Key"}

    try:
        result = await asyncio.wait_for(
            summarize_chat(
                transcript,
                api_key=llm["api_key"],
                base_url=llm["base_url"],
                model=llm["model"],
                memory=previous,
            ),
            timeout=30,
        )
    except Exception as exc:                      # 总结失败不影响主流程
        return {"summary": previous, "added": [], "skipped": f"总结失败：{exc}"}

    summary = (result.get("summary") or "").strip()[:600]
    memories = result.get("memories") or []

    added: list[dict] = []
    with db() as conn:
        # 同一段对话里内容完全一样的记忆不重复写
        existing = {
            r["content"]
            for r in conn.execute(
                "SELECT content FROM memories WHERE conversation_id = ?",
                (conversation_id,),
            )
        }
        for item in memories:
            content = item["content"]
            if content in existing:
                continue
            conn.execute(
                """INSERT INTO memories (user_id, conversation_id, kind, content)
                   VALUES (?, ?, ?, ?)""",
                (user["id"], conversation_id, item["kind"], content),
            )
            existing.add(content)
            added.append(item)
        conn.execute(
            """UPDATE conversations
                  SET summary = ?,
                      summarized_upto = summarized_upto + ?,
                      updated_at = datetime('now')
                WHERE id = ?""",
            (summary, len(lines), conversation_id),
        )

    with db() as conn:
        upto = conn.execute(
            "SELECT summarized_upto FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()["summarized_upto"]

    return {"summary": summary, "added": added, "summarized_upto": upto, "skipped": ""}


# ---------------------------------------------------------------------
# 记忆图谱：只读，给前台的「记忆」页面用
# ---------------------------------------------------------------------

@router.get("/{conversation_id}/memories")
def conversation_memories(conversation_id: int, request: Request):
    user = _me(request)
    with db() as conn:
        _owned(conn, conversation_id, user["id"])
        rows = conn.execute(
            """SELECT id, kind, content, created_at
                 FROM memories
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY id DESC""",
            (conversation_id, user["id"]),
        ).fetchall()
    return {"memories": [dict(r) for r in rows]}
