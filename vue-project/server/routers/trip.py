# =====================================================================
# routers/trip.py —— 预留：行程规划（待接入）
#   计划：POST /api/trip/plan  请求体 { destination, days, budget, prefs }
#        让模型输出结构化行程（JSON），存库后返回给前端的行程面板。
#   对应前端顶部导航条那 5 个空按钮里的「行程规划」。
# =====================================================================

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["trip"])

# @router.post("/trip/plan")
# async def plan_trip(body: TripIn):
#     ...
