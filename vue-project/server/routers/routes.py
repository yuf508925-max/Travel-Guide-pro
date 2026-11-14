# =====================================================================
# routers/routes.py —— 搜索记录（按账号隔离，行程和看视频共用一个表）
#   GET  /api/routes/last      最近一次搜索（没有就返回 {found: false}）
#   GET  /api/routes?limit=10  最近 N 条
#   POST /api/routes           保存一次搜索 { kind, city, origin, destination, mode }
#
# kind = "route" 是行程面板（城市 / 出发地 / 目的地 / 方式）
# kind = "vlog"  是「观看 vlog」的搜索词（关键词存在 origin，其它字段留空）
# 两类记录都在 route_searches 表里，用 kind 区分，各自只保留 20 条。
#
# 每个账号只看得到自己的记录；创建和删除都带账号条件，越权查不到也删不掉。
# =====================================================================

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import db
from .auth import current_user

router = APIRouter(prefix="/api/routes", tags=["routes"])

MAX_PER_USER = 20
MODES = {"driving", "walking", "transit"}
# route=行程、vlog=看视频关键词、vlog-region=看视频的地区、
# weather=天气里查过的城市、memory=记忆面板搜过的词
KINDS = ("route", "vlog", "vlog-region", "weather", "memory")


class RouteSearchIn(BaseModel):
    # 不传就是行程，保持老前端的请求体还能用
    kind: str = Field(default="route", max_length=16)
    city: str = Field(default="", max_length=40)
    origin: str = Field(..., min_length=1, max_length=120)
    destination: str = Field(default="", max_length=120)
    mode: str = Field(default="driving", max_length=20)


def _shape(row) -> dict:
    return {
        "id": row["id"],
        "kind": row["kind"] if "kind" in row.keys() else "route",
        "city": row["city"],
        "origin": row["origin"],
        "destination": row["destination"],
        "mode": row["mode"],
        "created_at": row["created_at"],
    }


def _kind(value: str) -> str:
    cleaned = (value or "").strip().lower()
    return cleaned if cleaned in KINDS else "route"


@router.get("/last")
def get_last(kind: str = Query("route"), user: dict = Depends(current_user)):
    """面板打开时调：把上次填的城市/出发地/目的地/方式（或上次搜的词）回填"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM route_searches WHERE user_id = ? AND kind = ? ORDER BY id DESC LIMIT 1",
            (user["id"], _kind(kind)),
        ).fetchone()

    if not row:
        return {"found": False}
    return {"found": True, "search": _shape(row)}


@router.get("")
def list_searches(
    limit: int = Query(10, ge=1, le=MAX_PER_USER),
    kind: str = Query("route"),
    user: dict = Depends(current_user),
):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM route_searches WHERE user_id = ? AND kind = ?"
            " ORDER BY id DESC LIMIT ?",
            (user["id"], _kind(kind), limit),
        ).fetchall()
    return {"searches": [_shape(r) for r in rows]}


@router.delete("/{search_id}")
def delete_search(search_id: int, user: dict = Depends(current_user)):
    """删除一条搜索记录（只能删自己的）"""
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM route_searches WHERE id = ? AND user_id = ?",
            (search_id, user["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "没有这条记录")
        conn.execute(
            "DELETE FROM route_searches WHERE id = ? AND user_id = ?",
            (search_id, user["id"]),
        )
    return {"ok": True}


@router.post("")
def save_search(body: RouteSearchIn, user: dict = Depends(current_user)):
    kind = _kind(body.kind)
    city = body.city.strip()
    origin = body.origin.strip()
    destination = body.destination.strip()
    mode = body.mode.strip() if body.mode.strip() in MODES else "driving"

    if not origin:
        raise HTTPException(400, "关键词不能为空")
    # 只有行程要城市 / 目的地 / 交通方式；其它分类只记一个关键词
    if kind == "route" and not destination:
        raise HTTPException(400, "出发地和目的地都要填")
    if kind != "route":
        city, destination, mode = "", "", ""

    with db() as conn:
        # 和同类的上一条完全一样就不重复存（避免连点"搜索"堆一堆）
        last = conn.execute(
            "SELECT city, origin, destination, mode FROM route_searches"
            " WHERE user_id = ? AND kind = ? ORDER BY id DESC LIMIT 1",
            (user["id"], kind),
        ).fetchone()
        if last and (
            last["city"] == city
            and last["origin"] == origin
            and last["destination"] == destination
            and last["mode"] == mode
        ):
            return {"ok": True, "deduped": True}

        # 同一个词（行程是「城市+出发地+目的地+方式」）只留最新一条：
        # 先把旧的删掉再插，列表里就不会出现两条一样的
        if kind == "route":
            conn.execute(
                "DELETE FROM route_searches WHERE user_id = ? AND kind = ?"
                " AND city = ? AND origin = ? AND destination = ? AND mode = ?",
                (user["id"], kind, city, origin, destination, mode),
            )
        else:
            conn.execute(
                "DELETE FROM route_searches WHERE user_id = ? AND kind = ? AND origin = ?",
                (user["id"], kind, origin),
            )

        conn.execute(
            """
            INSERT INTO route_searches (user_id, city, origin, destination, mode, kind)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user["id"], city, origin, destination, mode, kind),
        )

        # 每一类只留最近 20 条
        conn.execute(
            """
            DELETE FROM route_searches
             WHERE user_id = ? AND kind = ?
               AND id NOT IN (
                   SELECT id FROM route_searches
                    WHERE user_id = ? AND kind = ?
                    ORDER BY id DESC
                    LIMIT ?
               )
            """,
            (user["id"], kind, user["id"], kind, MAX_PER_USER),
        )

    return {"ok": True}
