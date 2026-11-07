# =====================================================================
# routers/providers.py —— 账号下的多套 API Key（提供商）
#   GET    /api/providers                列表 + 服务器默认值
#   POST   /api/providers                新增一套
#   PUT    /api/providers/{id}           修改（含切换模型）
#   DELETE /api/providers/{id}           删除
#   POST   /api/providers/{id}/activate  切到这套（聊天就用它）
#
#   一个账号可以有多套 Key；每套可以挂多个模型，选其中一个作为当前模型。
#   Key 在响应里永远是打码的（sk-ab••••wxyz）。
# =====================================================================

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import time
from datetime import datetime

from ..balance_check import fetch_balance
from ..db import db
from ..llm_settings import DEFAULTS, active_provider, list_providers, provider_to_dict, split_models
from ..provider_check import verify_credentials
from .auth import current_user

router = APIRouter(prefix="/api/providers", tags=["providers"])


class ProviderIn(BaseModel):
    name: str = Field(default="DeepSeek", max_length=40)
    # 新增时必填；编辑时不传或空串 = 沿用库里原来的 Key
    api_key: str | None = Field(default=None, max_length=200)
    base_url: str = Field(default="", max_length=300)
    # 候选模型：可以传字符串（逗号分隔）也可以传数组，统一按逗号存
    models: str | list[str] = Field(default="")
    # 当前选中的模型，留空就用 models 的第一个
    model: str = Field(default="", max_length=100)


def _clean(body: ProviderIn, existing: dict | None = None) -> dict:
    """校验 + 规整成可以直接入库的一行

    existing 不为空表示"编辑已有的一条"：api_key 不传/留空就沿用原值。
    """
    name = (body.name or "").strip() or "DeepSeek"
    base_url = (body.base_url or "").strip()

    raw_key = (body.api_key or "").strip()
    if raw_key:
        api_key = raw_key
    elif existing is not None:
        api_key = existing.get("api_key") or ""
    else:
        api_key = ""

    models = body.models if isinstance(body.models, list) else split_models(body.models)
    models = [m.strip() for m in models if isinstance(m, str) and m.strip()]
    # 去重保序 + 上限，别让人往里贴 200 个模型
    deduped: list[str] = []
    for m in models:
        if m not in deduped:
            deduped.append(m)
    models = deduped[:20]

    selected = (body.model or "").strip()
    if selected and models and selected not in models:
        models.insert(0, selected)
    if not selected and models:
        selected = models[0]

    if not api_key:
        raise HTTPException(400, "API Key 不能为空")
    if len(api_key) < 10:
        raise HTTPException(400, "API Key 看起来不对（太短了）")
    if any(ch.isspace() for ch in api_key):
        raise HTTPException(400, "API Key 中间不应该有空格")
    if base_url:
        if not base_url.startswith(("http://", "https://")):
            raise HTTPException(400, "Base URL 要以 http:// 或 https:// 开头")
        if any(ch.isspace() for ch in base_url):
            raise HTTPException(400, "Base URL 中间不应该有空格")

    return {
        "name": name,
        "api_key": api_key,
        "base_url": base_url,
        "models": ",".join(models),
        "model": selected,
    }


def _fetch(user_id: int, provider_id: int) -> dict:
    """取一条，顺带校验它确实属于当前用户（越权直接 404）"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM user_providers WHERE id = ? AND user_id = ?",
            (provider_id, user_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "没有这个提供商")
    return dict(row)


# 余额缓存：同一个 provider 60 秒内不重复查（余额不会一秒变一次）
BALANCE_TTL_SECONDS = 60
_balance_cache: dict[int, tuple[float, dict]] = {}


@router.get("/balance")
async def get_balance(
    provider_id: int | None = None,
    user: dict = Depends(current_user),
):
    """查当前这套 Key 的余额（不传 provider_id 就查正在使用的那套）"""
    if provider_id is not None:
        row = _fetch(user["id"], provider_id)

        # _fetch 返回的是数据库原始行，这里统一成 dict
        provider = row
    else:
        provider = active_provider(user["id"])
        if not provider:
            raise HTTPException(404, "还没有配置 API Key")

    now = time.monotonic()
    cached = _balance_cache.get(provider["id"])
    if cached and cached[0] > now:
        return cached[1]

    result = await fetch_balance(
        provider.get("api_key") or "",
        (provider.get("base_url") or "").strip() or DEFAULTS["base_url"],
    )
    result["provider"] = provider.get("name") or "DeepSeek"
    result["checked_at"] = datetime.now().strftime("%H:%M")
    _balance_cache[provider["id"]] = (now + BALANCE_TTL_SECONDS, result)
    return result


@router.get("")
def get_providers(user: dict = Depends(current_user)):
    return {
        "providers": list_providers(user["id"]),
        "defaults": {"base_url": DEFAULTS["base_url"], "model": DEFAULTS["model"]},
    }


async def _verify_or_400(api_key: str, base_url: str, model: str, name: str) -> dict:
    """保存前先打一次真实请求：通不过就不写库

    失败时 400 的 detail 是 {message, field}：
      field 告诉前端是哪一项写错了（api_key / base_url / model），用来标红对应输入框。
    """
    result = await verify_credentials(api_key, base_url or DEFAULTS["base_url"], model)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"「{name}」测试没通过，没有保存：{result.get('message', '未知错误')}",
                "field": result.get("field", ""),
            },
        )
    return result


@router.post("")
async def create_provider(body: ProviderIn, user: dict = Depends(current_user)):
    clean = _clean(body)
    verification = await _verify_or_400(
        clean["api_key"], clean["base_url"], clean["model"], clean["name"]
    )

    with db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM user_providers WHERE user_id = ?", (user["id"],)
        ).fetchone()[0]
        cur = conn.execute(
            """
            INSERT INTO user_providers (user_id, name, api_key, base_url, models, model, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                clean["name"],
                clean["api_key"],
                clean["base_url"],
                clean["models"],
                clean["model"],
                1 if count == 0 else 0,   # 第一套自动激活
            ),
        )
        provider_id = cur.lastrowid

    return {
        "provider": provider_to_dict(_fetch(user["id"], provider_id)),
        "verification": verification,
    }


@router.put("/{provider_id}")
async def update_provider(provider_id: int, body: ProviderIn, user: dict = Depends(current_user)):
    row = _fetch(user["id"], provider_id)      # 归属校验
    clean = _clean(body, existing=row)
    verification = await _verify_or_400(
        clean["api_key"], clean["base_url"], clean["model"], clean["name"]
    )

    with db() as conn:
        conn.execute(
            """
            UPDATE user_providers
               SET name = ?, api_key = ?, base_url = ?, models = ?, model = ?,
                   updated_at = datetime('now')
             WHERE id = ? AND user_id = ?
            """,
            (
                clean["name"],
                clean["api_key"],
                clean["base_url"],
                clean["models"],
                clean["model"],
                provider_id,
                user["id"],
            ),
        )
    return {
        "provider": provider_to_dict(_fetch(user["id"], provider_id)),
        "verification": verification,
    }


@router.delete("/{provider_id}")
def delete_provider(provider_id: int, user: dict = Depends(current_user)):
    row = _fetch(user["id"], provider_id)

    with db() as conn:
        conn.execute(
            "DELETE FROM user_providers WHERE id = ? AND user_id = ?",
            (provider_id, user["id"]),
        )
        # 删掉的正好是激活项 → 自动激活剩下最新的那套，聊天不会突然没配置
        if row["is_active"]:
            conn.execute(
                """
                UPDATE user_providers SET is_active = 1
                 WHERE id = (
                     SELECT id FROM user_providers
                      WHERE user_id = ?
                      ORDER BY updated_at DESC, id DESC
                      LIMIT 1
                 )
                """,
                (user["id"],),
            )
    return {"ok": True}


@router.post("/{provider_id}/activate")
def activate_provider(provider_id: int, user: dict = Depends(current_user)):
    _fetch(user["id"], provider_id)

    with db() as conn:
        conn.execute(
            "UPDATE user_providers SET is_active = 0 WHERE user_id = ?", (user["id"],)
        )
        conn.execute(
            "UPDATE user_providers SET is_active = 1 WHERE id = ? AND user_id = ?",
            (provider_id, user["id"]),
        )
    return {"ok": True}

class ModelIn(BaseModel):
    model: str = Field(..., min_length=1, max_length=100)


@router.post("/{provider_id}/model")
def set_provider_model(provider_id: int, body: ModelIn, user: dict = Depends(current_user)):
    """列表里那个模型下拉框：只切模型，不用重传 Key"""
    row = _fetch(user["id"], provider_id)
    models = split_models(row["models"])
    model = body.model.strip()
    if models and model not in models:
        raise HTTPException(400, "这个模型不在该提供商的模型列表里")

    with db() as conn:
        conn.execute(
            """
            UPDATE user_providers
               SET model = ?, updated_at = datetime('now')
             WHERE id = ? AND user_id = ?
            """,
            (model, provider_id, user["id"]),
        )
    return {"provider": provider_to_dict(_fetch(user["id"], provider_id))}
