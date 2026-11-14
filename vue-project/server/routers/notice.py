# =====================================================================
# notice.py —— 公告
# ---------------------------------------------------------------------
#   前台（所有登录用户）：GET  /api/notices        看公告列表
#   后台（仅管理员）：    POST /api/notices        发一条公告
#                        PATCH  /api/notices/{id} 改内容 / 置顶
#                        DELETE /api/notices/{id} 删除
#
# 公告是全局的（跟当前对话无关），所以不按 user_id 隔离；
# 已读状态存在前端 localStorage（记最后一次看过的公告 id），后端不记。
# =====================================================================

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import db
from .admin import AdminUser
from .auth import current_user

router = APIRouter(prefix="/api/notices", tags=["notices"])

MAX_TITLE = 60
MAX_CONTENT = 4000


class NoticeIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=MAX_TITLE)
    content: str = Field("", max_length=MAX_CONTENT)
    pinned: bool = False


class NoticePatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=MAX_TITLE)
    content: str | None = Field(None, max_length=MAX_CONTENT)
    pinned: bool | None = None


def _shape(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "content": row["content"],
        "pinned": bool(row["pinned"]),
        "publisher": row["publisher"],
        "created_at": row["created_at"],
    }


@router.get("")
def list_notices(
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(current_user),
):
    """登录后才能看（公告是给已登录用户的通知）。"""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM announcements ORDER BY pinned DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"notices": [_shape(r) for r in rows]}


@router.post("")
def create_notice(body: NoticeIn, admin: dict = AdminUser):
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "公告标题不能为空")

    with db() as conn:
        cur = conn.execute(
            "INSERT INTO announcements (title, content, pinned, publisher)"
            " VALUES (?, ?, ?, ?)",
            (title[:MAX_TITLE], body.content.strip()[:MAX_CONTENT],
             1 if body.pinned else 0, admin.get("username", "")),
        )
        row = conn.execute(
            "SELECT * FROM announcements WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _shape(row)


@router.patch("/{notice_id}")
def update_notice(notice_id: int, body: NoticePatch, admin: dict = AdminUser):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM announcements WHERE id = ?", (notice_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "没有这条公告")

        title = row["title"] if body.title is None else body.title.strip()
        content = row["content"] if body.content is None else body.content.strip()
        pinned = row["pinned"] if body.pinned is None else (1 if body.pinned else 0)
        if not title:
            raise HTTPException(400, "公告标题不能为空")

        conn.execute(
            "UPDATE announcements SET title = ?, content = ?, pinned = ? WHERE id = ?",
            (title[:MAX_TITLE], content[:MAX_CONTENT], pinned, notice_id),
        )
        fresh = conn.execute(
            "SELECT * FROM announcements WHERE id = ?", (notice_id,)
        ).fetchone()
    return _shape(fresh)


@router.delete("/{notice_id}")
def delete_notice(notice_id: int, admin: dict = AdminUser):
    with db() as conn:
        cur = conn.execute("DELETE FROM announcements WHERE id = ?", (notice_id,))
        if not cur.rowcount:
            raise HTTPException(404, "没有这条公告")
    return {"ok": True}
