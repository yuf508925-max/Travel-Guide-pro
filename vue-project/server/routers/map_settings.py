# =====================================================================
# routers/map_settings.py —— 高德地图 Key（单独一张表，一人一行）
#   GET /api/map   读当前账号的 Key / 安全密钥
#   PUT /api/map   保存（空字符串 = 清除）
#
# 存储：user_map_settings(user_id PK, amap_key, security_code, updated_at)
#   早期版本把这两个字段放在 user_providers 里，db.py 启动时会自动搬过来。
#   界面上仍然和聊天 Key 放在同一个「设置」面板里。
# =====================================================================

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..db import db
from .auth import current_user

router = APIRouter(prefix="/api/map", tags=["map"])


class MapSettingsIn(BaseModel):
    amap_key: str = Field(default="", max_length=200)
    security_code: str = Field(default="", max_length=200)


@router.get("")
def get_map_settings(user: dict = Depends(current_user)):
    with db() as conn:
        row = conn.execute(
            "SELECT amap_key, security_code, updated_at FROM user_map_settings WHERE user_id = ?",
            (user["id"],),
        ).fetchone()

    if not row:
        return {"amap_key": "", "security_code": "", "updated_at": ""}
    return {
        "amap_key": row["amap_key"] or "",
        "security_code": row["security_code"] or "",
        "updated_at": row["updated_at"] or "",
    }


@router.put("")
def put_map_settings(body: MapSettingsIn, user: dict = Depends(current_user)):
    key = body.amap_key.strip()
    code = body.security_code.strip()

    with db() as conn:
        conn.execute(
            """
            INSERT INTO user_map_settings (user_id, amap_key, security_code, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                amap_key      = excluded.amap_key,
                security_code = excluded.security_code,
                updated_at    = excluded.updated_at
            """,
            (user["id"], key, code),
        )

    return {"ok": True, "amap_key": key, "security_code": code}