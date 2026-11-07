# =====================================================================
# provider_check.py —— 保存前先验一次：这套 Key / 地址 / 模型到底通不通
# ---------------------------------------------------------------------
# 只做"发个很轻的请求看会不会被拒"，不读写数据库；
# 路由层（routers/providers.py）调它，失败就不写入。
#
# 为什么一定要真发一次对话请求：
#   很多中转的 /models 列表是"大目录"，比这个 Key 实际能调用的模型多得多
#   （实测：列表里 182 个，对话接口只认 2 个）。只看列表会放过用不了的模型。
#   所以 /models 只用来快速验 Key + 连通性，最终以 max_tokens=1 的真实请求为准。
#
# 返回带 field，告诉前端是哪一项写错了：
#   "api_key"   Key 没填 / 无效
#   "base_url"  地址连不上 / 路径不对
#   "model"     模型名不对（会把上游"支持哪些模型"的原话带回来）
#
# 只用标准库 urllib，放在线程里跑，不阻塞事件循环。
# =====================================================================

import asyncio
import json
import urllib.error
import urllib.request

TIMEOUT = 10.0

CHAT_PAYLOAD = {
    "messages": [{"role": "user", "content": "ping"}],
    "max_tokens": 1,
    "stream": False,
}


def _join(base: str, path: str) -> str:
    return base.rstrip("/") + path


def _request(method: str, url: str, api_key: str, payload: dict | None = None) -> tuple[int, dict | None]:
    """发一次请求，返回 (状态码, 解析后的 JSON)；4xx/5xx 不抛异常"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "fufu-travel/0.1 (+provider-check)",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ConnectionError("连不上这个地址，检查 Base URL 或网络")

    try:
        return status, json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return status, None


def _error_detail(data: dict | None) -> str:
    if not isinstance(data, dict):
        return ""
    err = data.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or "")[:220]
    if isinstance(err, str):
        return err[:220]
    return ""


def _chat_probe(base: str, key: str, model: str) -> dict:
    """用一次 max_tokens=1 的真实请求确认「Key + 模型」都能用"""
    payload = dict(CHAT_PAYLOAD, model=model)
    try:
        status, data = _request("POST", _join(base, "/chat/completions"), key, payload)
    except ConnectionError as exc:
        return {"ok": False, "field": "base_url", "message": str(exc)}

    if status == 200:
        return {
            "ok": True,
            "field": "",
            "message": f"测试通过：Key 有效，模型「{model}」能正常调用",
            "checked": "chat",
        }

    if status in (401, 403):
        return {
            "ok": False,
            "field": "api_key",
            "message": "Key 无效或没有权限（401/403），请检查是否复制完整",
        }

    detail = _error_detail(data)

    if status in (400, 404):
        # 上游提到 model 就是模型名的问题（原话里通常还会列出支持的模型）
        if "model" in detail.lower():
            return {
                "ok": False,
                "field": "model",
                "message": f"这个模型用不了：{detail or 'HTTP ' + str(status)}",
            }
        return {
            "ok": False,
            "field": "base_url",
            "message": f"接口不认这个地址：{detail or 'HTTP ' + str(status)}",
        }

    return {
        "ok": False,
        "field": "base_url",
        "message": f"接口返回 HTTP {status}：{detail or '未知错误'}",
    }


def _verify_sync(api_key: str, base_url: str, model: str) -> dict:
    key = (api_key or "").strip()
    base = (base_url or "").strip()
    wanted = (model or "").strip()

    if not key:
        return {"ok": False, "field": "api_key", "message": "还没有填 API Key"}

    # ---- 1. /models：快速确认 Key 与地址（顺便告诉我们接口在不在） ----
    models_count = 0
    try:
        status, data = _request("GET", _join(base, "/models"), key)
    except ConnectionError as exc:
        return {"ok": False, "field": "base_url", "message": str(exc)}

    if status == 200:
        if isinstance(data, dict):
            models_count = len(data.get("data") or [])
    elif status in (401, 403):
        return {
            "ok": False,
            "field": "api_key",
            "message": "Key 无效或没有权限（401/403），请检查是否复制完整",
        }
    elif status not in (404, 405, 501):
        return {
            "ok": False,
            "field": "base_url",
            "message": f"接口返回 HTTP {status}，检查一下 Base URL",
        }

    # ---- 2. 最终以真实对话请求为准（没填模型就用内置默认） ----
    result = _chat_probe(base, key, wanted or "deepseek-chat")
    if result["ok"] and models_count:
        result["message"] = (
            f"{result['message']}（接口共列出 {models_count} 个模型）"
        )
    return result


async def verify_credentials(api_key: str, base_url: str, model: str = "") -> dict:
    """异步入口：把同步检查扔到线程池里

    返回：{ok, field, message, models?}
    """
    return await asyncio.to_thread(_verify_sync, api_key, base_url, model)
