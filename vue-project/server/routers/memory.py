# =====================================================================
# routers/memory.py —— 记忆可视化 / 管理
# ---------------------------------------------------------------------
#   表：memories(id, user_id, conversation_id, kind, content, created_at)
#   · 一条对话对应多条记忆；删对话时级联删除（ON DELETE CASCADE）
#   · kind: fact / preference / plan / place / event / summary
#
#   接口：
#     GET    /api/memories            列表 + 统计（?q= 搜索，?conversation_id= 只看某段对话）
#     GET    /api/memories/conversations  可切换的对话清单（带记忆条数）
#     GET    /api/memories/graph      知识图谱（节点 + 边）
#     DELETE /api/memories/{id}       删掉某条记忆
# =====================================================================

from fastapi import APIRouter, HTTPException, Request

from ..db import db
from .auth import optional_user

router = APIRouter(prefix="/api/memories", tags=["memories"])

KIND_LABELS = {
    "fact": "事实",
    "preference": "偏好",
    "plan": "计划",
    "place": "地点",
    "event": "事件",
    "summary": "对话摘要",
}


def _me(request: Request) -> dict:
    user = optional_user(request)
    if user is None:
        raise HTTPException(401, "请先登录")
    return user


def _conversation_rows(conn, user_id: int, only_id: int | None) -> list[dict]:
    """我有哪些对话，各存了几条记忆（没有记忆的对话也列出来，方便切换）"""
    sql = """
        SELECT c.id, c.title,
               (SELECT COUNT(*) FROM memories m WHERE m.conversation_id = c.id) AS n
          FROM conversations c
         WHERE c.user_id = ?
    """
    params: list = [user_id]
    if only_id is not None:
        sql += " AND c.id = ?"
        params.append(only_id)
    sql += " ORDER BY c.updated_at DESC, c.id DESC"
    return [
        {"id": r["id"], "title": r["title"] or "对话", "count": r["n"]}
        for r in conn.execute(sql, params).fetchall()
    ]


@router.get("")
def list_memories(request: Request, q: str = "", conversation_id: int | None = None):
    """一段对话的记忆 + 统计。

    · conversation_id 必传（不传只是管理员排查用，前端永远带）
    · q 只在记忆内容（概括）里模糊匹配，不匹配对话名
    """
    user = _me(request)
    keyword = q.strip()

    with db() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.kind, m.content, m.created_at,
                   m.conversation_id, c.title AS conversation_title
              FROM memories m
              JOIN conversations c ON c.id = m.conversation_id
             WHERE m.user_id = ?
             ORDER BY m.id DESC
            """,
            (user["id"],),
        ).fetchall()
        conversation_list = _conversation_rows(conn, user["id"], None)

    items = [
        {
            "id": r["id"],
            "kind": r["kind"],
            "kind_label": KIND_LABELS.get(r["kind"], r["kind"]),
            "content": r["content"],
            "created_at": r["created_at"],
            "conversation_id": r["conversation_id"],
            "conversation_title": r["conversation_title"] or "对话",
        }
        for r in rows
    ]

    if conversation_id is not None:
        items = [m for m in items if m["conversation_id"] == conversation_id]

    if keyword:
        low = keyword.lower()
        items = [m for m in items if low in m["content"].lower()]

    by_kind: dict[str, int] = {}
    conv_ids: set[int] = set()
    for m in items:
        by_kind[m["kind"]] = by_kind.get(m["kind"], 0) + 1
        conv_ids.add(m["conversation_id"])

    return {
        "memories": items,
        "conversations": conversation_list,
        "stats": {
            "total": len(items),
            "conversations": len(conv_ids),
            "by_kind": [
                {"kind": k, "label": KIND_LABELS.get(k, k), "count": v}
                for k, v in sorted(by_kind.items(), key=lambda kv: -kv[1])
            ],
        },
    }


@router.get("/conversations")
def memory_conversations(request: Request):
    """记忆页顶部的对话切换器数据"""
    user = _me(request)
    with db() as conn:
        return {"conversations": _conversation_rows(conn, user["id"], None)}


@router.get("/graph")
def memory_graph(request: Request, conversation_id: int):
    """给可视化用的图：对话是枢纽，记忆挂在它下面。

    记忆按对话严格隔离：必须指定 conversation_id，不会把多段对话混在一起。
    每个记忆节点带三个指标：
      · 连接度 degree —— 和它同类型（kind）的其它记忆有多少条
      · 条目   items  —— 这段对话一共有多少条记忆
      · 权重   weight —— 1 + 1.5 × 连接度，保留两位（同类型越多，关联越强）
    """
    user = _me(request)
    with db() as conn:
        owned = conn.execute(
            "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user["id"]),
        ).fetchone()
        if owned is None:
            raise HTTPException(404, "对话不存在")

        rows = conn.execute(
            """
            SELECT m.id, m.kind, m.content, m.conversation_id, c.title
              FROM memories m
              JOIN conversations c ON c.id = m.conversation_id
             WHERE m.user_id = ? AND m.conversation_id = ?
             ORDER BY m.id DESC
             LIMIT 400
            """,
            (user["id"], conversation_id),
        ).fetchall()

    def weight_of(degree: int) -> float:
        return round(1 + 1.5 * degree, 2)

    total_items = len(rows)
    title = rows[0]["title"] if rows else "对话"

    hub = {
        "id": f"conv-{conversation_id}",
        "label": title or "对话",
        "type": "conversation",
        "kind": "conversation",
        "degree": total_items,
        "items": total_items,
        "weight": weight_of(total_items),
        "neighbors": [
            {"id": f"mem-{r['id']}", "label": r["content"], "weight": 1.0} for r in rows[:12]
        ],
    }

    nodes: list[dict] = [hub]
    edges: list[dict] = []
    by_kind: dict[str, list[dict]] = {}
    for r in rows:
        by_kind.setdefault(r["kind"], []).append(dict(r))

    for r in rows:
        node_id = f"mem-{r['id']}"
        siblings = [s for s in by_kind[r["kind"]] if s["id"] != r["id"]]
        degree = len(siblings)
        weight = weight_of(degree)
        nodes.append(
            {
                "id": node_id,
                "label": r["content"],
                "type": "memory",
                "kind": r["kind"],
                "kind_label": KIND_LABELS.get(r["kind"], r["kind"]),
                "degree": degree,
                "items": total_items,
                "weight": weight,
                "neighbors": [
                    {
                        "id": f"mem-{s['id']}",
                        "label": s["content"],
                        "weight": weight,
                    }
                    for s in siblings[:12]
                ],
            }
        )
        edges.append({"source": hub["id"], "target": node_id, "weight": 1.0})
        # 同类型的记忆之间也连一条：这就是「关联记忆」的来源
        for s in siblings[:6]:
            if s["id"] > r["id"]:
                continue
            edges.append(
                {"source": node_id, "target": f"mem-{s['id']}", "weight": weight}
            )

    return {"nodes": nodes, "edges": edges, "conversation_id": conversation_id}


@router.delete("/{memory_id}")
def delete_memory(memory_id: int, request: Request):
    user = _me(request)
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM memories WHERE id = ? AND user_id = ?",
            (memory_id, user["id"]),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "记忆不存在")
        conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    return {"ok": True}
