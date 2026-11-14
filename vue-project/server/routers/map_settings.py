# =====================================================================
# routers/map_settings.py —— 高德地图 Key（管理员在后台配，全局一份）
#   GET /api/map          登录用户取这份配置（前端加载 JS API 时用）
#   GET /api/admin/map    后台读（含更新时间 / 改的人）
#   PUT /api/admin/map    后台改（只有管理员）
#
# 为什么不按账号存：
#   这是「Web端(JS API)」的 Key，它最终一定要出现在浏览器加载的脚本地址里，
#   不是机密。全站统一一份，管理员在后台改一次，所有用户立即生效，
#   也不用担心用户自己填错类型（选成 Web服务 / Android 之类）。
#
# 为什么放数据库而不是 server/config.py：
#   改 Key 不用改代码、不用重启后端；而且这个仓库会发给别人，
#   谁的高德 Key 都不该写死在源码里。
# =====================================================================

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import db
from .admin import AdminUser
from .auth import current_user

router = APIRouter(prefix="/api", tags=["map"])

KEY_AMAP = "amap_key"
KEY_SECURITY = "amap_security_code"


def read_setting(conn, key: str) -> tuple[str, str, str]:
    """读一条配置 → (值, 改的人, 更新时间)。没有就返回空串。"""
    row = conn.execute(
        "SELECT value, updated_by, updated_at FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    if row is None:
        return "", "", ""
    return row["value"] or "", row["updated_by"] or "", row["updated_at"] or ""


def write_setting(conn, key: str, value: str, who: str) -> None:
    conn.execute(
        """
        INSERT INTO app_settings (key, value, updated_by, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET
            value      = excluded.value,
            updated_by = excluded.updated_by,
            updated_at = excluded.updated_at
        """,
        (key, value, who),
    )


class MapConfig(BaseModel):
    amap_key: str = Field(default="", max_length=128)
    security_code: str = Field(default="", max_length=128)


@router.get("/map")
def get_map_settings(user: dict = Depends(current_user)):
    """当前登录账号拿到的高德配置（所有账号看到的是同一份）。"""
    with db() as conn:
        key, _, updated_at = read_setting(conn, KEY_AMAP)
        code, _, _ = read_setting(conn, KEY_SECURITY)
    return {"amap_key": key, "security_code": code, "updated_at": updated_at}


@router.get("/admin/map")
def admin_get_map(user: dict = AdminUser):
    """后台读配置：多返回「谁改的、什么时候改的」，方便确认是不是生效了。"""
    with db() as conn:
        key, by_key, at_key = read_setting(conn, KEY_AMAP)
        code, _, at_code = read_setting(conn, KEY_SECURITY)
    return {
        "amap_key": key,
        "security_code": code,
        "updated_by": by_key,
        "updated_at": at_key or at_code,
        "configured": bool(key.strip()),
    }


@router.put("/admin/map")
def admin_save_map(payload: MapConfig, user: dict = AdminUser):
    key = payload.amap_key.strip()
    code = payload.security_code.strip()
    if not key:
        raise HTTPException(400, "高德地图 Key 不能为空")

    with db() as conn:
        write_setting(conn, KEY_AMAP, key, user["username"])
        write_setting(conn, KEY_SECURITY, code, user["username"])

    return {"ok": True, "configured": True}


@router.delete("/admin/map")
def admin_clear_map(user: dict = AdminUser):
    """清空 Key：清掉之后前端会提示「管理员还没配置」，行程面板不可用。"""
    with db() as conn:
        write_setting(conn, KEY_AMAP, "", user["username"])
        write_setting(conn, KEY_SECURITY, "", user["username"])
    return {"ok": True, "configured": False}
