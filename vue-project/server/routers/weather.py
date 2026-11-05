# =====================================================================
# routers/weather.py —— 天气接口
#   GET /api/weather?city=青岛&days=7
#     返回：{ city, region, current{...}, days[{date, weekday, ...}] }
#   数据源是 Open-Meteo（免费、不需要 Key），具体请求在 providers/weather.py。
#   这里只做三件事：参数校验、结果缓存、把异常翻成好懂的 HTTP 错误。
# =====================================================================

import time

from fastapi import APIRouter, HTTPException, Query

from ..providers import weather as weather_provider
from ..providers.weather import CityNotFound, WeatherUnavailable

router = APIRouter(prefix="/api", tags=["weather"])

# 缓存：同一个（省, 市）10 分钟内不重复打上游（天气变化没那么快，
# 也避免用户连点按钮把免费额度刷爆）。key = (省, 市, 天数)
CACHE_TTL_SECONDS = 600
_cache: dict[tuple[str, str, int], tuple[float, dict]] = {}


@router.get("/weather")
async def get_weather(
    province: str = Query("", max_length=20, description="省份，可选，用来区分同名城市，如 山东"),
    city: str = Query("青岛", min_length=1, max_length=40, description="城市名，中文/拼音都行"),
    days: int = Query(7, ge=1, le=14, description="未来几天，1~14"),
):
    """查未来天气。失败时：404 = 城市认不出，502 = 上游天气服务不可用"""
    city = city.strip()
    province = province.strip()
    key = (province, city, days)
    now = time.monotonic()

    cached = _cache.get(key)
    if cached and cached[0] > now:
        return cached[1]

    try:
        data = await weather_provider.get_weather(city, province, days)
    except CityNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"没找到城市「{city}」，换个写法试试（比如「青岛」而不是「青岛栈桥」）",
        )
    except WeatherUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # 顺手清掉过期条目，别让 dict 无限长大
    for stale in [k for k, (expire, _) in _cache.items() if expire <= now]:
        _cache.pop(stale, None)

    _cache[key] = (now + CACHE_TTL_SECONDS, data)
    return data