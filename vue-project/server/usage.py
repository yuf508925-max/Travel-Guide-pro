# =====================================================================
# usage.py —— 调用打点（谁、什么时候、调了哪一类接口）
# ---------------------------------------------------------------------
# 打点分三种来源：
#   1. 页面访问  前端 App 挂载时 POST /api/visit        → kind='visit'
#   2. 高德调用  前端每次用 AMap 的服务时 POST /api/usage/amap → kind='amap'
#   3. 后端接口  app.py 的中间件按路径分类自动记          → chat / tts / trains …
#
# 这里只负责「写一行」，聚合统计都在 routers/admin.py 里做 SQL。
# 任何打点失败都不能影响主请求，所以调用处统一 try/except 吞掉。
# =====================================================================

import sqlite3
import time

from .db import USAGE_RETENTION, db, purge_old_usage

# 打点表只留一年：启动时 db.init_db 会清一次，服务一直跑着的话这里每天再兜一次
PURGE_INTERVAL = 24 * 3600
_last_purge = 0.0

# 路径前缀 → 调用类别（越具体的放前面）
KIND_RULES: list[tuple[str, str]] = [
    ("/api/chat", "chat"),
    ("/api/tts", "tts"),
    ("/api/trains", "trains"),
    ("/api/weather", "weather"),
    ("/api/routes", "routes"),
    ("/api/providers", "providers"),
    ("/api/map", "map"),
    ("/api/poster", "poster"),
    ("/api/trip", "trip"),
    ("/api/auth", "auth"),
    ("/api/feedback", "feedback"),
    ("/api/music", "music"),
]

KIND_LABELS = {
    "visit": "网页访问",
    "amap": "高德地图",
    "chat": "AI 对话",
    "tts": "语音合成",
    "trains": "动车班次",
    "weather": "天气查询",
    "routes": "行程记录",
    "providers": "模型 Key",
    "map": "地图配置",
    "poster": "旅行一图流",
    "trip": "行程规划",
    "auth": "登录注册",
    "feedback": "意见反馈",
    "music": "电脑里的音乐",
    "chat_key": "模型对话",
    "tts_key": "语音播报",
    "other": "其它接口",
}


def kind_of(path: str) -> str:
    for prefix, kind in KIND_RULES:
        if path.startswith(prefix):
            return kind
    return "other"


def user_id_from_token(conn: sqlite3.Connection, token: str | None) -> int | None:
    """Cookie 里的 token → user_id（失效或没有就返回 None）"""
    if not token:
        return None
    row = conn.execute(
        "SELECT user_id FROM sessions WHERE token = ? AND expires_at > datetime('now')",
        (token,),
    ).fetchone()
    return int(row["user_id"]) if row else None


def record(
    *,
    kind: str,
    detail: str = "",
    user_id: int | None = None,
    token: str | None = None,
) -> None:
    """记一行打点。user_id 优先，没有就按 token 查。

    user_id 是必填的：认不出是谁（没登录 / token 过期 / 匿名请求）就整行不写，
    免得统计里出现一堆 user_id 是 NULL 的数据。
    """
    global _last_purge

    with db() as conn:
        uid = user_id if user_id is not None else user_id_from_token(conn, token)
        if uid is None:
            return
        conn.execute(
            "INSERT INTO usage_events (user_id, kind, detail, expires_at)"
            " VALUES (?, ?, ?, datetime('now', ?))",
            (uid, kind, detail[:80], USAGE_RETENTION),
        )

        # 顺手做过期清理（每天最多一次，失败也不影响这次打点）
        now = time.monotonic()
        if now - _last_purge >= PURGE_INTERVAL:
            _last_purge = now
            try:
                purge_old_usage(conn)
            except Exception:
                pass
