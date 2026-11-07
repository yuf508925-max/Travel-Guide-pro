# =====================================================================
# routers/auth.py —— 注册 / 登录 / 登出 / 当前用户
# ---------------------------------------------------------------------
# 会话机制：登录成功后生成一个随机 token 存进 sessions 表，
# 并把 token 放进 HttpOnly Cookie。浏览器之后每次请求自动带上，
# 后端从 request.cookies 里读 token 查库，就知道是谁。
# 这样不依赖 itsdangerous，也不把用户信息放进 Cookie。
# =====================================================================

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..db import db
from ..security import hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_COOKIE = "fufu_session"
SESSION_DAYS = 7


class RegisterIn(BaseModel):
    """注册：用户名/密码有最低长度要求"""
    username: str = Field(..., min_length=2, max_length=32)
    password: str = Field(..., min_length=6, max_length=64)


class LoginIn(BaseModel):
    """登录：只要求非空。

    ★ 密码长度约束只属于注册。如果登录也写 min_length=6，
      用户输一个短的错误密码会先触发 422 校验错误，
      前端拿到的是数组形式的 detail，就会显示成 [object Object]。
    """
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


def _create_session(conn, user_id: int) -> str:
    """生成本次登录的 token，写入 sessions 表（顺便清理过期会话）"""
    token = secrets.token_urlsafe(32)  # 256 位随机，足够不可猜
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires),
    )
    return token


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,      # JS 读不到，防 XSS 偷 token
        samesite="lax",     # 防 CSRF
        secure=False,       # 本地 http 开发用 False；上线（HTTPS）改 True
        path="/",
    )


@router.post("/register")
def register(body: RegisterIn, response: Response):
    username = body.username.strip()
    if not username:
        raise HTTPException(400, "用户名不能为空")

    with db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if exists:
            raise HTTPException(409, "用户名已存在")

        cur = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, hash_password(body.password)),
        )
        user_id = cur.lastrowid
        token = _create_session(conn, user_id)

    # 注册完直接登录
    _set_session_cookie(response, token)
    return {"username": username}


@router.post("/login")
def login(body: LoginIn, response: Response):
    with db() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (body.username.strip(),),
        ).fetchone()

        # 统一提示，不告诉攻击者"用户到底存不存在"
        if not row or not verify_password(body.password, row["password_hash"]):
            raise HTTPException(401, "用户名或密码错误")

        token = _create_session(conn, row["id"])

    _set_session_cookie(response, token)
    return {"username": row["username"]}


@router.get("/me")
def me(request: Request):
    """刷新页面时前端调它，Cookie 有效就返回当前用户"""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "未登录")

    with db() as conn:
        row = conn.execute(
            """
            SELECT u.username
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > datetime('now')
            """,
            (token,),
        ).fetchone()

    if not row:
        raise HTTPException(401, "登录已过期")
    return {"username": row["username"]}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


# ---------------------------------------------------------------------
# 取当前登录用户，给需要登录的接口用：
#   current_user   未登录直接 401
#   optional_user  未登录返回 None（比如聊天：登录了就用账号里的 Key，
#                  没登录就没有 Key，聊天会返回"请先登录"）
# ---------------------------------------------------------------------
def optional_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None

    with db() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.username
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > datetime('now')
            """,
            (token,),
        ).fetchone()

    if not row:
        return None
    return {"id": row["id"], "username": row["username"]}


def current_user(request: Request) -> dict:
    user = optional_user(request)
    if user is None:
        raise HTTPException(401, "登录已过期，请重新登录")
    return user


def require_user(request: Request) -> str:
    """只要用户名（老接口用）"""
    return current_user(request)["username"]
