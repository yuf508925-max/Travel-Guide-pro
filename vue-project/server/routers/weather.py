# =====================================================================
# routers/weather.py —— 预留：天气 / 地图数据（待接入）
#   计划：GET /api/weather?city=xxx   查目的地天气
#        GET /api/places?city=xxx    查景点地理位置
#   这类是外部数据源，和 AI 无关，单独放一个 provider。
# =====================================================================

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["weather"])

# @router.get("/weather")
# async def weather(city: str):
#     ...
