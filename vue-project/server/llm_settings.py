# =====================================================================
# llm_settings.py —— 账号的模型配置（多套 Key / 多个模型）
# ---------------------------------------------------------------------
# 数据长什么样：user_providers 表，一个账号可以有多行，每行是一套 Key：
#   name / api_key / base_url / models（逗号分隔的候选模型）/ model（当前用的）
#   is_active = 1 的那一行，就是聊天当前使用的
#
# 唯一来源：当前激活的 provider。
#   没有配置就返回 api_key=None，聊天接口会回一句"先去设置里填 Key"。
# =====================================================================

from fastapi import Request

from . import keyvault
from .config import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from .db import db
from .routers.auth import optional_user

# 用户留空时用的内置默认值（写死在 config.py）
DEFAULTS = {"base_url": DEEPSEEK_BASE_URL, "model": DEEPSEEK_MODEL}


def mask_key(key: str) -> str:
    """界面上只露头尾：sk-ab••••wxyz"""
    if not key:
        return ""
    if len(key) <= 12:
        return "••••••"
    return f"{key[:5]}••••{key[-4:]}"


def split_models(raw: str) -> list[str]:
    """逗号（中英文都行）分隔的模型串 → 列表，顺手去重保序"""
    out: list[str] = []
    for piece in (raw or "").replace("，", ",").split(","):
        name = piece.strip()
        if name and name not in out:
            out.append(name)
    return out


def provider_to_dict(row) -> dict:
    """数据库行 → 前端友好的结构（Key 解密后打码，原文不出后端）"""
    models = split_models(row["models"])
    selected = (row["model"] or "").strip()
    # 老数据可能只有 model 没有 models，这里补齐，界面上下拉才有选项
    if selected and selected not in models:
        models.insert(0, selected)
    plain_key = keyvault.decrypt_text(row["api_key"])
    return {
        "id": row["id"],
        "name": row["name"] or "DeepSeek",
        "api_key_masked": mask_key(plain_key),
        "has_api_key": bool(plain_key),
        "key_fingerprint": keyvault.fingerprint(plain_key),
        "base_url": row["base_url"] or "",
        "models": models,
        "model": selected or (models[0] if models else ""),
        "is_active": bool(row["is_active"]),
        "updated_at": row["updated_at"],
    }


def list_providers(user_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM user_providers WHERE user_id = ? ORDER BY is_active DESC, id ASC",
            (user_id,),
        ).fetchall()
    return [provider_to_dict(r) for r in rows]


def active_provider(user_id: int) -> dict | None:
    """当前激活的那套（没有激活的就退第一条）"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM user_providers WHERE user_id = ? ORDER BY is_active DESC, id ASC LIMIT 1",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def resolve_llm(request: Request) -> dict:
    """聊天前调用：算出这次请求该用哪套配置（只认账号里激活的那套）

    返回 {api_key, base_url, model}：
      api_key 为 None 表示这个账号还没配过，provider 会报一句人话
    """
    user = optional_user(request)
    row = active_provider(user["id"]) if user else None

    api_key = keyvault.decrypt_text((row or {}).get("api_key")).strip()
    base_url = ((row or {}).get("base_url") or "").strip() or DEFAULTS["base_url"]

    # 模型：先看选中的，再看列表第一个，最后用内置默认
    model = ((row or {}).get("model") or "").strip()
    if not model:
        models = split_models((row or {}).get("models") or "")
        model = models[0] if models else ""

    return {
        "api_key": api_key or None,
        "base_url": base_url,
        "model": model or DEFAULTS["model"],
        # 打点用：哪个 Key 的哪一档模型
        "provider_id": (row or {}).get("id"),
        "provider_name": (row or {}).get("name") or "",
        # 当前登录账号（对话记忆按它归属）
        "user_id": (user or {}).get("id"),
    }
