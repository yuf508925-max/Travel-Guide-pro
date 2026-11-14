# =====================================================================
# agent_tools.py —— 给大模型用的「工具」（function calling）
# ---------------------------------------------------------------------
# 这里把项目里已有的能力包成模型能调用的函数：
#   get_weather   查天气        → providers/weather.py（Open-Meteo，不用 Key）
#   query_trains  查火车/高铁    → train_check.py（12306）
#   plan_route    规划两地路线   → 本地城市表定位 + OSRM 算驾车距离/时长
#
# 为什么行程不直接调高德？
#   高德那个 Key 是「Web端 (JS API)」类型的，只能在浏览器里用；
#   服务端调 restapi.amap.com 会直接返回 USERKEY_PLAT_NOMATCH（实测过）。
#   所以服务端这边用 OSRM（开源路线服务，免 Key）算距离和驾车时间，
#   市内公交/地铁这种精细方案还是交给前端的高德面板。
#
# 约定：所有工具都返回 dict，失败时返回 {"ok": False, "error": "人话原因"}，
#       不抛异常 —— 模型看到 error 会用自己的话告诉用户，而不是整轮对话崩掉。
# =====================================================================

import asyncio
import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request

from .providers import weather as weather_provider
from .providers.weather import CityNotFound, WeatherUnavailable
from . import train_check
from .train_check import TrainError

OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
OSRM_TIMEOUT = 12.0
OSRM_UA = "fufu-travel/0.1 (+route tool)"

# 工具名 → 给用户看的中文（前端「正在查天气…」用这个）
LABELS = {
    "get_weather": "查天气",
    "query_trains": "查火车班次",
    "plan_route": "规划路线",
}

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "查询某个城市未来几天的天气预报（真实数据，不是猜的）。"
                "用户问天气、要不要带伞、某天适不适合出门、行程排哪天更合适时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名，中文，例如「青岛」「大理」「东京」",
                    },
                    "days": {
                        "type": "integer",
                        "description": "要查几天，1~7，默认 7",
                    },
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_trains",
            "description": (
                "查询两个城市之间的火车/高铁班次（来自 12306 的真实余票查询）。"
                "用户问怎么坐车过去、几点的车、还有没有票、跨城交通时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_city": {"type": "string", "description": "出发城市，例如「厦门」"},
                    "to_city": {"type": "string", "description": "到达城市，例如「福州」"},
                    "date": {
                        "type": "string",
                        "description": "出发日期，YYYY-MM-DD；也可以说「今天」「明天」「后天」，不填默认明天",
                    },
                },
                "required": ["from_city", "to_city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_route",
            "description": (
                "规划两地之间的路线，返回直线距离、驾车里程和大概开多久。"
                "用户问「从A到B多远/要开多久/怎么去」时调用。"
                "地点写城市名或区内小地名都行；认不出的地名会返回错误，别硬编数字。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "出发地，例如「青岛」「青岛市南区」"},
                    "destination": {"type": "string", "description": "目的地，例如「崂山」「烟台」"},
                    "city": {
                        "type": "string",
                        "description": "可选：这两地所在的城市，用来消歧同名地点",
                    },
                },
                "required": ["origin", "destination"],
            },
        },
    },
]

# ---------------------------------------------------------------------
# 地点定位：先查项目内置的城市表（快、准、不用网），不行再让 Open-Meteo 兜底
# ---------------------------------------------------------------------
_PLACE_SUFFIXES = ("火车站", "高铁站", "机场", "车站", "站", "市中心")


def _candidates(text: str) -> list[str]:
    """「青岛市南区」→ [青岛市南区, 青岛, 市南] ... 逐个试，能认出来一个就够"""
    raw = (text or "").strip().replace(" ", "")
    out: list[str] = []

    def push(value: str) -> None:
        value = value.strip()
        if value and value not in out and len(value) >= 2:
            out.append(value)

    push(raw)
    for suffix in _PLACE_SUFFIXES:
        if raw.endswith(suffix) and len(raw) > len(suffix):
            push(raw[: -len(suffix)])

    # 「XX市南区」「XX市栈桥」这种：把城市名抠出来单独试一次
    for suffix in ("区", "县", "市"):
        if suffix in raw[1:]:
            push(raw[: raw.index(suffix)])
            break

    for suffix in ("市", "区", "县", "省"):
        if raw.endswith(suffix) and len(raw) > len(suffix) + 1:
            push(raw[: -len(suffix)])
    return out


async def _locate(text: str, province: str = "") -> dict:
    """地名 → {name, lat, lng, region}；认不出来抛 ValueError"""
    tried: list[str] = []
    for candidate in _candidates(text):
        tried.append(candidate)
        try:
            name, lat, lon, region = await weather_provider.geocode(candidate, province)
            return {"name": name, "lat": lat, "lng": lon, "region": region}
        except CityNotFound:
            continue
        except WeatherUnavailable:
            break
    raise ValueError(
        f"没能定位「{text}」。换成城市名或区名再试试（比如「青岛」「市南区」），"
        "太小的景点名我这边查不到坐标"
    )


# ---------------------------------------------------------------------
# OSRM：给两个坐标，返回驾车里程（米）和时长（秒）
# ---------------------------------------------------------------------
def _osrm_sync(a: dict, b: dict) -> dict:
    coords = f"{a['lng']},{a['lat']};{b['lng']},{b['lat']}"
    url = f"{OSRM_URL}/{urllib.parse.quote(coords, safe=',;')}?overview=false&alternatives=false"
    request = urllib.request.Request(url, headers={"User-Agent": OSRM_UA})
    try:
        with urllib.request.urlopen(request, timeout=OSRM_TIMEOUT) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"路线服务返回 {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("路线服务连不上，检查一下网络") from exc

    try:
        data = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("路线服务返回的数据看不懂") from exc

    routes = data.get("routes") or []
    if not routes:
        raise RuntimeError("没算出路线（这两点之间可能没有可通行的道路）")
    route = routes[0]
    distance = float(route.get("distance") or 0)
    duration = float(route.get("duration") or 0)
    return {"distance_m": distance, "duration_s": duration}


def _fmt_minutes(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    if minutes < 60:
        return f"{minutes} 分钟"
    hours, rest = divmod(minutes, 60)
    return f"{hours} 小时 {rest} 分" if rest else f"{hours} 小时"


def _fmt_km(meters: float) -> float:
    return round(meters / 1000, 1)


# ---------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------
async def _tool_get_weather(args: dict) -> dict:
    city = str(args.get("city") or "").strip()
    if not city:
        return {"ok": False, "error": "要告诉我查哪个城市的天气"}

    try:
        days = int(args.get("days") or 7)
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(7, days))

    try:
        data = await weather_provider.get_weather(city, "", days)
    except CityNotFound:
        return {"ok": False, "error": f"没找到城市「{city}」，换个写法试试（比如「青岛」而不是「青岛栈桥」）"}
    except WeatherUnavailable as exc:
        return {"ok": False, "error": str(exc)}

    current = data.get("current") or {}
    return {
        "ok": True,
        "city": data.get("city"),
        "region": data.get("region"),
        "updated_at": data.get("updated_at"),
        "current": {
            "temp_c": current.get("temp"),
            "desc": current.get("desc"),
            "wind_kmh": current.get("wind"),
            "humidity": current.get("humidity"),
        },
        "days": [
            {
                "date": day.get("date"),
                "weekday": day.get("weekday"),
                "desc": day.get("desc"),
                "temp_max": day.get("temp_max"),
                "temp_min": day.get("temp_min"),
                "rain_prob": day.get("rain_prob"),
            }
            for day in (data.get("days") or [])
        ],
    }


_RELATIVE_DAYS = {"今天": 0, "今日": 0, "明天": 1, "明日": 1, "后天": 2, "大后天": 3}


def _normalize_date(raw: str) -> str:
    text = (raw or "").strip()
    today = dt.date.today()
    if not text:
        return (today + dt.timedelta(days=1)).isoformat()
    if text in _RELATIVE_DAYS:
        return (today + dt.timedelta(days=_RELATIVE_DAYS[text])).isoformat()
    return text   # 交给 train_check 校验格式


async def _tool_query_trains(args: dict) -> dict:
    from_city = str(args.get("from_city") or "").strip()
    to_city = str(args.get("to_city") or "").strip()
    if not from_city or not to_city:
        return {"ok": False, "error": "出发城市和到达城市都要有"}

    date = _normalize_date(str(args.get("date") or ""))
    try:
        data = await train_check.fetch_trains(from_city, to_city, date)
    except TrainError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:                    # 12306 的接口偶尔抽风，别把对话带崩
        return {"ok": False, "error": f"查车次时出了点问题：{exc}"}

    trains = []
    for row in (data.get("trains") or [])[:8]:
        trains.append(
            {
                "code": row.get("code"),
                "kind": row.get("kind"),
                "depart": row.get("depart"),
                "arrive": row.get("arrive"),
                "duration": row.get("duration"),
                "second": row.get("second"),
                "first": row.get("first"),
                "business": row.get("business"),
            }
        )

    return {
        "ok": True,
        "date": data.get("date"),
        "from_station": data.get("from_station"),
        "to_station": data.get("to_station"),
        "total": data.get("total"),
        "trains": trains,
        "note": "" if trains else "这一天这两个站之间没查到车次，可能日期太远（12306 只预售 15 天内）或该站不停",
    }


async def _tool_plan_route(args: dict) -> dict:
    origin = str(args.get("origin") or "").strip()
    destination = str(args.get("destination") or "").strip()
    city = str(args.get("city") or "").strip()
    if not origin or not destination:
        return {"ok": False, "error": "出发地和目的地都要有"}

    try:
        start = await _locate(origin, city)
        end = await _locate(destination, city)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    if abs(start["lat"] - end["lat"]) < 1e-6 and abs(start["lng"] - end["lng"]) < 1e-6:
        return {"ok": False, "error": "出发地和目的地是同一个地方，换一个目的地吧"}

    try:
        route = await asyncio.to_thread(_osrm_sync, start, end)
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "origin": {"name": start["name"], "lat": start["lat"], "lng": start["lng"]},
        "destination": {"name": end["name"], "lat": end["lat"], "lng": end["lng"]},
        "distance_km": _fmt_km(route["distance_m"]),
        "driving_minutes": int(round(route["duration_s"] / 60)),
        "driving_time": _fmt_minutes(route["duration_s"]),
        "note": "这是驾车路线（OSRM 开源路网）的里程和耗时，不含堵车和休息；市內公交/地铁方案请用行程面板",
    }


_EXECUTORS = {
    "get_weather": _tool_get_weather,
    "query_trains": _tool_query_trains,
    "plan_route": _tool_plan_route,
}


def label_of(name: str) -> str:
    return LABELS.get(name, name)


async def execute(name: str, arguments: str | dict) -> dict:
    """执行一个工具调用。arguments 是模型给的 JSON 字符串（也可能是 dict）"""
    if isinstance(arguments, dict):
        args = arguments
    else:
        raw = (arguments or "").strip()
        if not raw:
            args = {}
        else:
            try:
                args = json.loads(raw)
            except ValueError:
                return {"ok": False, "error": f"参数不是合法 JSON：{raw[:120]}"}
            if not isinstance(args, dict):
                return {"ok": False, "error": "参数必须是对象"}

    executor = _EXECUTORS.get(name)
    if executor is None:
        return {"ok": False, "error": f"没有这个工具：{name}"}

    try:
        return await executor(args)
    except Exception as exc:                    # 兜底：工具出错也只告诉模型，不 500
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
