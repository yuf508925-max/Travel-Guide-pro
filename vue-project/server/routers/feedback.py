# =====================================================================
# routers/feedback.py —— 前台「设置 → 意见反馈」提交给管理员
#   提交  POST /api/feedback
#   查看/标记/删除在 routers/admin.py（只有管理员看得到）
# =====================================================================

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import db
from .auth import optional_user

router = APIRouter(prefix="/api", tags=["feedback"])


class FeedbackIn(BaseModel):
    content: str = Field(min_length=4, max_length=2000)


@router.post("/feedback")
def submit(body: FeedbackIn, request: Request):
    user = optional_user(request)
    if user is None:
        raise HTTPException(401, "登录后才能反馈")

    text = body.content.strip()
    if len(text) < 4:
        raise HTTPException(400, "再多写几个字吧")

    with db() as conn:
        # 一天只能发一条（按 UTC 自然日算，和库里 created_at 一致）
        today_count = conn.execute(
            """
            SELECT COUNT(*) AS n FROM feedback
             WHERE user_id = ? AND date(created_at) = date('now')
            """,
            (user["id"],),
        ).fetchone()["n"]
        if today_count:
            raise HTTPException(429, "今天已经发过一条反馈了，明天再来吧")

        # 同一个人 1 分钟内不重复提交同一段内容（防手抖连点）
        dup = conn.execute(
            """
            SELECT id FROM feedback
             WHERE user_id = ? AND content = ?
               AND created_at > datetime('now', '-1 minute')
            """,
            (user["id"], text),
        ).fetchone()
        if dup:
            return {"ok": True, "id": dup["id"], "duplicated": True}

        cur = conn.execute(
            "INSERT INTO feedback (user_id, username, content) VALUES (?, ?, ?)",
            (user["id"], user["username"], text),
        )
        new_id = cur.lastrowid

    return {"ok": True, "id": new_id, "duplicated": False}
