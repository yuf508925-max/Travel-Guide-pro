# =====================================================================
# routers/admin.py —— 后台管理接口（只有管理员能进）
# ---------------------------------------------------------------------
# 这里对应课件里「Spring Session + HandlerInterceptor」那一套，换成本项目的
# FastAPI 写法，四步一一对应：
#
#   1. 登录接口把「你是谁」写进 Session
#      → routers/auth.py 的 login：成功后往 sessions 表插一行 token，
#        浏览器只拿到 HttpOnly Cookie（对应 session.setAttribute("loginUser", user)）
#
#   2. 拦截器：每个请求进门先查 Session
#      → 下面的 require_admin()：从 Cookie 里取 token → 查 sessions JOIN users，
#        没登录 401、不是管理员 403 —— 等价于 preHandle 里 return false
#
#   3. 注册拦截器：指定「拦谁、放谁」
#      → app.py 里 include_router(admin.router) 时整组挂 depend，
#        只有 /api/admin/** 被拦；登录、聊天、天气这些不拦（等价于 addPathPatterns）
#
#   4. 页面读 Session
#      → GET /api/auth/me 返回当前用户和 role，前端据此决定显不显示「后台管理」
# =====================================================================

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..db import db
from ..security import hash_password
from ..usage import KIND_LABELS
from .auth import optional_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------
# 拦截器本体
# ---------------------------------------------------------------------
def require_admin(request: Request) -> dict:
    """没登录 → 401；登录了但不是 admin → 403。

    前端拿到这两种状态分别做「跳登录」和「提示没有权限」。
    """
    user = optional_user(request)
    if user is None:
        raise HTTPException(401, "登录已过期，请重新登录")
    if user.get("role") != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


AdminUser = Depends(require_admin)


class UserPatch(BaseModel):
    """只允许改这两样：角色、密码。用户名不可改（改了历史数据就对不上了）。"""

    role: Literal["user", "admin"] | None = None
    password: str | None = Field(default=None, min_length=6, max_length=64)


def _admin_count(conn: sqlite3.Connection, exclude: int | None = None) -> int:
    sql = "SELECT COUNT(*) AS n FROM users WHERE role = 'admin'"
    params: tuple = ()
    if exclude is not None:
        sql += " AND id <> ?"
        params = (exclude,)
    return int(conn.execute(sql, params).fetchone()["n"])


@router.get("/overview")
def overview(user: dict = AdminUser):
    """后台首页的四个数字卡"""
    with db() as conn:
        row = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM users)                          AS users,
              (SELECT COUNT(*) FROM users WHERE role = 'admin')     AS admins,
              (SELECT COUNT(*) FROM sessions
                WHERE expires_at > datetime('now'))                 AS sessions,
              (SELECT COUNT(*) FROM user_providers)                 AS providers,
              (SELECT COUNT(*) FROM route_searches)                 AS routes
            """
        ).fetchone()

    return {
        "users": row["users"],
        "admins": row["admins"],
        "sessions": row["sessions"],
        "providers": row["providers"],
        "routes": row["routes"],
        "me": {"id": user["id"], "username": user["username"]},
    }


@router.get("/users")
def list_users(
    q: str = Query("", max_length=64),
    user: dict = AdminUser,
):
    """用户列表：搜索、各自的 Key 数 / 行程记录数 / 调用量"""
    keyword = q.strip()
    like = f"%{keyword}%"

    with db() as conn:
        rows = conn.execute(
            """
            SELECT u.id,
                   u.username,
                   u.role,
                   u.created_at,
                   (SELECT COUNT(*) FROM user_providers p WHERE p.user_id = u.id) AS providers,
                   (SELECT COUNT(*) FROM route_searches r WHERE r.user_id = u.id)  AS routes,
                   (SELECT COUNT(*) FROM usage_events e
                     WHERE e.user_id = u.id AND e.kind NOT IN ('visit'))            AS calls,
                   (SELECT COUNT(*) FROM feedback f WHERE f.user_id = u.id)        AS feedback
              FROM users u
             WHERE (? = '' OR u.username LIKE ?)
             ORDER BY (u.role = 'admin') DESC, u.id ASC
            """,
            (keyword, like),
        ).fetchall()

    return {
        "total": len(rows),
        "users": [
            {
                "id": row["id"],
                "username": row["username"],
                "role": row["role"],
                "created_at": row["created_at"],
                "providers": row["providers"],
                "routes": row["routes"],
                "calls": row["calls"],
                "feedback": row["feedback"],
                "is_me": row["id"] == user["id"],
            }
            for row in rows
        ],
    }


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, user: dict = AdminUser):
    """改角色 / 重置密码。两个保护：不能把自己降级、不能把最后一个管理员降级。"""
    with db() as conn:
        target = conn.execute(
            "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if target is None:
            raise HTTPException(404, "用户不存在")

        if body.role is not None and body.role != target["role"]:
            if target["id"] == user["id"] and body.role != "admin":
                raise HTTPException(400, "不能取消自己的管理员权限")
            if target["role"] == "admin" and _admin_count(conn, exclude=target["id"]) == 0:
                raise HTTPException(400, "至少要留一个管理员")
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (body.role, user_id))

        if body.password:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(body.password), user_id),
            )

        updated = conn.execute(
            "SELECT id, username, role, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()

    return {
        "id": updated["id"],
        "username": updated["username"],
        "role": updated["role"],
        "created_at": updated["created_at"],
    }


@router.delete("/users/{user_id}")
def delete_user(user_id: int, user: dict = AdminUser):
    """删账号：sessions / providers / route_searches / tts 设置靠外键级联一起删。"""
    if user_id == user["id"]:
        raise HTTPException(400, "不能删除当前登录的账号")

    with db() as conn:
        target = conn.execute(
            "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if target is None:
            raise HTTPException(404, "用户不存在")
        if target["role"] == "admin" and _admin_count(conn, exclude=target["id"]) == 0:
            raise HTTPException(400, "至少要留一个管理员")

        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    return {"ok": True, "username": target["username"]}


# =====================================================================
# 模型库：管理员维护「认识哪些模型」，前台/后台都能用来自查
# =====================================================================
MODEL_KIND_LABELS = {"chat": "语言模型", "tts": "语音合成模型"}


class ModelIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    vendor: str = Field("", max_length=40)
    kind: Literal["chat", "tts"] = "chat"


@router.get("/models")
def list_models(q: str = Query("", max_length=40), user: dict = AdminUser):
    """支持按名字 / 厂商模糊搜索，返回时带上中文类型名。"""
    like = f"%{q.strip()}%"
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, name, vendor, kind, created_at
              FROM model_catalog
             WHERE name LIKE ? OR vendor LIKE ?
             ORDER BY kind DESC, name COLLATE NOCASE
            """,
            (like, like),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "vendor": row["vendor"],
            "kind": row["kind"],
            "kind_label": MODEL_KIND_LABELS.get(row["kind"], row["kind"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


@router.post("/models")
def add_model(body: ModelIn, user: dict = AdminUser):
    """新增模型；同名已存在时直接返回那一条（幂等）。"""
    name = body.name.strip()
    with db() as conn:
        exists = conn.execute(
            "SELECT id, name, vendor, kind, created_at FROM model_catalog WHERE name = ?",
            (name,),
        ).fetchone()
        if exists:
            row = exists
        else:
            cur = conn.execute(
                "INSERT INTO model_catalog (name, vendor, kind) VALUES (?, ?, ?)",
                (name, body.vendor.strip(), body.kind),
            )
            row = conn.execute(
                "SELECT id, name, vendor, kind, created_at FROM model_catalog WHERE id = ?",
                (cur.lastrowid,),
            ).fetchone()
    return {
        "id": row["id"],
        "name": row["name"],
        "vendor": row["vendor"],
        "kind": row["kind"],
        "kind_label": MODEL_KIND_LABELS.get(row["kind"], row["kind"]),
        "created_at": row["created_at"],
    }


@router.delete("/models/{model_id}")
def delete_model(model_id: int, user: dict = AdminUser):
    with db() as conn:
        row = conn.execute(
            "SELECT name FROM model_catalog WHERE id = ?", (model_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "模型不存在")
        conn.execute("DELETE FROM model_catalog WHERE id = ?", (model_id,))
    return {"ok": True, "name": row["name"]}


# =====================================================================
# 统计：访问量 / 高德调用 / 各接口调用量 / 每个用户的明细
# =====================================================================
def _resolve_range(days: int, start: str, end: str):
    """把 (days | start+end) 解析成 [日期列表] 和边界字符串，供各统计接口共用"""
    import datetime as _dt

    if start and end:
        try:
            first = _dt.date.fromisoformat(start)
            last = _dt.date.fromisoformat(end)
        except ValueError:
            raise HTTPException(400, "日期格式要写成 YYYY-MM-DD")
        if last < first:
            raise HTTPException(400, "结束日期不能早于开始日期")
        if (last - first).days + 1 > 400:
            raise HTTPException(400, "区间最多 400 天")
    else:
        last = _dt.date.today()
        first = last - _dt.timedelta(days=days - 1)

    day_list = [(first + _dt.timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]
    return day_list, day_list[0], day_list[-1]


@router.get("/analytics")
def analytics(
    days: int = Query(7, ge=1, le=400),
    start: str = Query("", max_length=10),
    end: str = Query("", max_length=10),
    user: dict = AdminUser,
):
    """后台顶部的折线 / 柱状 / 环形数据。

    三种时间范围：
      · 近 N 天      GET /api/admin/analytics?days=7|30|365
      · 自定义区间   GET /api/admin/analytics?start=2026-10-01&end=2026-11-11
    """
    # ---- 1) 先把要统计的日期区间算出来 ----
    day_list, first_s, last_s = _resolve_range(days, start, end)

    def fill(rows) -> list[dict]:
        """把 SQL 的 (日期, 次数) 补成完整的每一天序列，缺失的补 0"""
        seen = {row["d"]: row["n"] for row in rows}
        return [{"date": d, "count": seen.get(d, 0)} for d in day_list]

    def series_by_kind(conn, kind: str) -> list[dict]:
        rows = conn.execute(
            """
            SELECT date(created_at) AS d, COUNT(*) AS n
              FROM usage_events
             WHERE kind = ? AND date(created_at) BETWEEN ? AND ?
             GROUP BY d
            """,
            (kind, first_s, last_s),
        ).fetchall()
        return fill(rows)

    with db() as conn:
        visits = series_by_kind(conn, "visit")
        amap = series_by_kind(conn, "amap")
        weather = series_by_kind(conn, "weather")

        by_kind = [
            {"kind": row["kind"], "label": KIND_LABELS.get(row["kind"], row["kind"]), "count": row["n"]}
            for row in conn.execute(
                """
                SELECT kind, COUNT(*) AS n
                  FROM usage_events
                 WHERE kind NOT IN ('visit', 'auth', 'other', 'chat_key', 'tts_key')
                   AND date(created_at) BETWEEN ? AND ?
                 GROUP BY kind
                 ORDER BY n DESC
                """,
                (first_s, last_s),
            )
        ]

        totals = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM usage_events WHERE kind = 'visit')                       AS visits,
              (SELECT COUNT(*) FROM usage_events WHERE kind = 'amap')                        AS amap,
              (SELECT COUNT(*) FROM usage_events
                WHERE kind NOT IN ('visit','amap'))                                          AS api,
              (SELECT COUNT(*) FROM usage_events
                WHERE kind = 'visit' AND date(created_at) = date('now'))                     AS visits_today,
              (SELECT COUNT(*) FROM usage_events
                WHERE kind = 'amap' AND date(created_at) = date('now'))                      AS amap_today,
              (SELECT COUNT(*) FROM usage_events WHERE kind = 'weather')                     AS weather,
              (SELECT COUNT(*) FROM usage_events
                WHERE kind = 'weather' AND date(created_at) = date('now'))                   AS weather_today,
              (SELECT COUNT(*) FROM feedback WHERE status = 'new')                           AS feedback_new
            """
        ).fetchone()

        # ---- 2) 每个「Key + 模型」在这个区间里的用量 ----
        raw_keys = conn.execute(
            """
            SELECT detail, date(created_at) AS d, COUNT(*) AS n
              FROM usage_events
             WHERE kind IN ('chat_key', 'tts_key') AND date(created_at) BETWEEN ? AND ?
             GROUP BY detail, d
            """,
            (first_s, last_s),
        ).fetchall()

        bucket: dict[str, dict] = {}
        for row in raw_keys:
            detail = row["detail"] or ""
            if detail.startswith("tts|"):
                pid, model = None, detail[4:]
            else:
                raw_pid, _, model = detail.partition("|")
                pid = int(raw_pid) if raw_pid.isdigit() else None
            item = bucket.setdefault(
                detail,
                {
                    "key": detail,
                    "provider_id": pid,
                    "model": model,
                    "is_tts": detail.startswith("tts|"),
                    "total": 0,
                    "by_day": {d: 0 for d in day_list},
                },
            )
            item["total"] += row["n"]
            if row["d"] in item["by_day"]:
                item["by_day"][row["d"]] = row["n"]

        names = {
            row["id"]: row["name"]
            for row in conn.execute("SELECT id, name FROM user_providers")
        }
        # 模型库里登记过、但还没产生调用的模型也列出来（total=0），
        # 这样 TTS 之类「配置了但还没用过」的模型也能在勾选面板里看到
        catalog_rows = conn.execute(
            "SELECT name, vendor, kind FROM model_catalog"
        ).fetchall()
        for row in catalog_rows:
            if row["kind"] == "tts":
                detail = f"tts|{row['name']}"
            else:
                detail = f"catalog|{row['name']}"
            if detail in bucket:
                continue
            bucket[detail] = {
                "key": detail,
                "provider_id": None,
                "model": row["name"],
                "is_tts": row["kind"] == "tts",
                "is_catalog": True,
                "vendor": row["vendor"],
                "total": 0,
                "by_day": {d: 0 for d in day_list},
            }

        keys = []
        for item in sorted(bucket.values(), key=lambda x: -x["total"])[:12]:
            if item.get("is_catalog"):
                provider = item.get("vendor") or ("语音 TTS" if item["is_tts"] else "模型库")
            elif item["is_tts"]:
                provider = "语音 TTS"
            else:
                provider = names.get(item["provider_id"]) or (
                    f"已删除的 Key #{item['provider_id']}" if item["provider_id"] else "未配置"
                )
            keys.append(
                {
                    "key": item["key"],
                    "provider": provider,
                    "model": item["model"] or "默认模型",
                    "is_tts": item["is_tts"],
                    "total": item["total"],
                    "data": [item["by_day"][d] for d in day_list],
                }
            )

    return {
        "start": first_s,
        "end": last_s,
        "days": len(day_list),
        "visits": visits,
        "amap": amap,
        "weather": weather,
        "keys": keys,
        "by_kind": by_kind,
        "totals": dict(totals),
    }


@router.get("/users/{user_id}/usage")
def user_usage(
    user_id: int,
    days: int = Query(7, ge=1, le=400),
    start: str = Query("", max_length=10),
    end: str = Query("", max_length=10),
    user: dict = AdminUser,
):
    """点开某个用户时看的明细：每类接口调用量 + 每天曲线 + 最近记录

    时间范围与总览一致：?days=7|30|365 或 ?start=2026-10-01&end=2026-11-11
    """
    day_list, first_s, last_s = _resolve_range(days, start, end)
    span = (first_s, last_s)

    with db() as conn:
        target = conn.execute(
            "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if target is None:
            raise HTTPException(404, "用户不存在")

        by_kind = [
            {
                "kind": row["kind"],
                "label": KIND_LABELS.get(row["kind"], row["kind"]),
                "count": row["n"],
            }
            for row in conn.execute(
                """
                SELECT kind, COUNT(*) AS n
                  FROM usage_events
                 WHERE user_id = ? AND kind NOT IN ('visit')
                   AND date(created_at) BETWEEN ? AND ?
                 GROUP BY kind
                 ORDER BY n DESC
                """,
                (user_id, *span),
            )
        ]

        seen = {
            row["d"]: row["n"]
            for row in conn.execute(
                """
                SELECT date(created_at) AS d, COUNT(*) AS n
                  FROM usage_events
                 WHERE user_id = ? AND kind NOT IN ('visit')
                   AND date(created_at) BETWEEN ? AND ?
                 GROUP BY d
                """,
                (user_id, *span),
            )
        }
        by_day = [{"date": d, "count": seen.get(d, 0)} for d in day_list]

        # 每类接口的每日曲线（右侧折线按勾选的类别画线）
        per_kind: dict[str, dict[str, int]] = {}
        for row in conn.execute(
            """
            SELECT kind, date(created_at) AS d, COUNT(*) AS n
              FROM usage_events
             WHERE user_id = ? AND kind NOT IN ('visit')
               AND date(created_at) BETWEEN ? AND ?
             GROUP BY kind, d
            """,
            (user_id, *span),
        ):
            per_kind.setdefault(row["kind"], {})[row["d"]] = row["n"]

        series = [
            {
                "kind": item["kind"],
                "label": item["label"],
                "data": [per_kind.get(item["kind"], {}).get(d, 0) for d in day_list],
            }
            for item in by_kind
        ]

        recent = [
            {"kind": row["kind"], "detail": row["detail"], "at": row["created_at"]}
            for row in conn.execute(
                """
                SELECT kind, detail, created_at
                  FROM usage_events
                 WHERE user_id = ? AND kind NOT IN ('visit')
                   AND date(created_at) BETWEEN ? AND ?
                 ORDER BY id DESC
                 LIMIT 12
                """,
                (user_id, *span),
            )
        ]

        total = conn.execute(
            """
            SELECT COUNT(*) AS n FROM usage_events
             WHERE user_id = ? AND kind NOT IN ('visit')
               AND date(created_at) BETWEEN ? AND ?
            """,
            (user_id, *span),
        ).fetchone()["n"]

        amap_total = conn.execute(
            """
            SELECT COUNT(*) AS n FROM usage_events
             WHERE user_id = ? AND kind = 'amap'
               AND date(created_at) BETWEEN ? AND ?
            """,
            (user_id, *span),
        ).fetchone()["n"]

    return {
        "user": {"id": target["id"], "username": target["username"], "role": target["role"]},
        "start": first_s,
        "end": last_s,
        "days": len(day_list),
        "total": total,
        "amap": amap_total,
        "by_kind": by_kind,
        "by_day": by_day,
        "series": series,
        "recent": recent,
    }


# =====================================================================
# 用户反馈（前台「设置 → 意见反馈」写进来）
# =====================================================================
@router.get("/feedback")
def list_feedback(
    status: str = Query("", max_length=16),
    user: dict = AdminUser,
):
    with db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM feedback WHERE status = ? ORDER BY id DESC LIMIT 100",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM feedback ORDER BY (status = 'new') DESC, id DESC LIMIT 100"
            ).fetchall()

    return {
        "total": len(rows),
        "feedback": [
            {
                "id": row["id"],
                "username": row["username"],
                "content": row["content"],
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in rows
        ],
    }


@router.patch("/feedback/{feedback_id}")
def update_feedback(feedback_id: int, user: dict = AdminUser):
    """点一下「已读 / 未读」来回切"""
    with db() as conn:
        row = conn.execute("SELECT id, status FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "这条反馈不存在")
        next_status = "new" if row["status"] == "read" else "read"
        conn.execute("UPDATE feedback SET status = ? WHERE id = ?", (next_status, feedback_id))
    return {"id": feedback_id, "status": next_status}


@router.delete("/feedback/{feedback_id}")
def delete_feedback(feedback_id: int, user: dict = AdminUser):
    with db() as conn:
        row = conn.execute("SELECT id FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "这条反馈不存在")
        conn.execute("DELETE FROM feedback WHERE id = ?", (feedback_id,))
    return {"ok": True}
