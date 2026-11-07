# =====================================================================
# balance_check.py —— 查当前这套 Key 还剩多少钱
# ---------------------------------------------------------------------
# 余额接口不是标准，各家路径/字段都不一样，这里按 Base URL 分流：
#
#   api.deepseek.com      GET /user/balance        → balance_infos[]
#   openrouter.ai         GET /credits             → data.total_credits / total_usage
#   moonshot / kimi       GET /users/me/balance    → data.available_balance ...
#   siliconflow           GET /user/info           → data.totalBalance / balance
#   其它（中转/兼容接口）  先按 DeepSeek 的 /user/balance 试一次，
#                         404 就如实返回"这个接口不支持余额查询"
#
# 只用标准库 urllib，放在线程里跑，不阻塞事件循环。
# =====================================================================

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 8.0


def _vendor_of(base_url: str) -> str:
    host = urllib.parse.urlparse(base_url).netloc.lower()
    if "openrouter.ai" in host:
        return "openrouter"
    if "moonshot" in host or "kimi" in host:
        return "kimi"
    if "siliconflow" in host:
        return "siliconflow"
    return "deepseek"


def _request_json(url: str, api_key: str) -> tuple[int, dict | None]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "fufu-travel/0.1 (+balance)",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ConnectionError("连不上接口")

    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return 200, None
    return 200, data if isinstance(data, dict) else None


def _num_str(value) -> str | None:
    """把 10 / "10.5" / None 统一成字符串（保留原样，别丢精度）"""
    if value is None:
        return None
    return str(value)


def _shape_deepseek(data: dict) -> dict:
    infos = data.get("balance_infos")
    if isinstance(infos, list) and infos:
        info = infos[0] if isinstance(infos[0], dict) else {}
        return {
            "ok": True,
            "currency": info.get("currency") or "CNY",
            "total": _num_str(info.get("total_balance")),
            "details": [
                {"label": "赠金", "value": _num_str(info.get("granted_balance")) or "0"},
                {"label": "充值", "value": _num_str(info.get("topped_up_balance")) or "0"},
            ],
        }

    for field in ("total_balance", "balance", "remain"):
        if field in data:
            return {
                "ok": True,
                "currency": data.get("currency") or "CNY",
                "total": _num_str(data.get(field)),
                "details": [],
            }
    return {"ok": False, "message": "接口没有返回余额字段"}


def _shape_openrouter(data: dict) -> dict:
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    credits = inner.get("total_credits")
    usage = inner.get("total_usage")
    if credits is None:
        return {"ok": False, "message": "接口没有返回额度字段"}

    total = None
    if isinstance(credits, (int, float)) and isinstance(usage, (int, float)):
        total = round(float(credits) - float(usage), 4)

    return {
        "ok": True,
        "currency": "USD",
        "total": _num_str(total if total is not None else credits),
        "details": [
            {"label": "总额度", "value": _num_str(credits)},
            {"label": "已用", "value": _num_str(usage)},
        ],
    }


def _shape_kimi(data: dict) -> dict:
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    available = inner.get("available_balance")
    if available is None:
        for field in ("balance", "cash_balance", "voucher_balance"):
            if field in inner:
                available = inner[field]
                break
    if available is None:
        return {"ok": False, "message": "接口没有返回余额字段"}

    return {
        "ok": True,
        "currency": "CNY",
        "total": _num_str(available),
        "details": [
            {"label": "现金", "value": _num_str(inner.get("cash_balance")) or "—"},
            {"label": "代金券", "value": _num_str(inner.get("voucher_balance")) or "—"},
        ],
    }


def _shape_siliconflow(data: dict) -> dict:
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    total = inner.get("totalBalance", inner.get("balance"))
    if total is None:
        return {"ok": False, "message": "接口没有返回余额字段"}

    return {
        "ok": True,
        "currency": "CNY",
        "total": _num_str(total),
        "details": [
            {"label": "充值余额", "value": _num_str(inner.get("chargeBalance")) or "—"},
        ],
    }


def _fetch_sync(api_key: str, base_url: str) -> dict:
    key = (api_key or "").strip()
    base = (base_url or "").strip().rstrip("/")
    if not key:
        return {"ok": False, "message": "还没有配置 API Key"}

    vendor = _vendor_of(base)
    paths = {
        "deepseek": ("/user/balance", _shape_deepseek),
        "openrouter": ("/credits", _shape_openrouter),
        "kimi": ("/users/me/balance", _shape_kimi),
        "siliconflow": ("/user/info", _shape_siliconflow),
    }
    path, shaper = paths[vendor]

    try:
        status, data = _request_json(base + path, key)
    except ConnectionError:
        return {"ok": False, "vendor": vendor, "message": "连不上接口"}

    if status in (401, 403):
        return {"ok": False, "vendor": vendor, "message": "Key 无效或没有权限"}
    if status == 404:
        return {"ok": False, "vendor": vendor, "message": "这个接口不支持余额查询"}
    if status != 200 or data is None:
        return {"ok": False, "vendor": vendor, "message": f"查询失败（HTTP {status}）"}

    result = shaper(data)
    result["vendor"] = vendor
    return result


async def fetch_balance(api_key: str, base_url: str) -> dict:
    """异步入口：{ok, vendor, currency?, total?, details?, message?}"""
    return await asyncio.to_thread(_fetch_sync, api_key, base_url)
