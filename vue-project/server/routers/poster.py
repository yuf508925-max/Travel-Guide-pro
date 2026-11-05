# =====================================================================
# routers/poster.py —— 预留：旅行一图流（待接入）
#   计划：POST /api/poster/plan  请求体 { destination, days, budget, prefs }
#        让模型输出结构化的行程要点，再由前端（canvas / html2canvas）
#        或后端（Pillow / playwright 截图）拼成一张可保存、可分享的长图，
#        返回图片 URL 给前端「旅行一图流」面板展示。
#   接入时先在 providers/ 下新建 poster.py 负责出图和存储，这里再实现路由。
#   对应前端顶部导航条的「旅行一图流」按钮。
# =====================================================================

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["poster"])

# @router.post("/poster/plan")
# async def plan_poster(body: PosterIn):
#     """生成一张行程长图：返回 { "image_url": "/static/posters/xxx.png" }"""
#     ...
