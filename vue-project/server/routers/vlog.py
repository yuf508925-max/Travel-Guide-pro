# =====================================================================
# routers/vlog.py —— 「观看 vlog」面板的数据接口
#   GET /api/vlog/recommend?region=青岛&seen=BV1,BV2&limit=5
#
# 一次请求做三件事：
#   ① 让模型把「青岛」想成几条像真人的搜索词（不要直接搜城市名，
#      那样出来的是新闻和航拍，不是旅行记录）；
#   ② 拿这些词去 B 站搜（全部按「综合」排序，保相关性），合并去重；
#   ③ 先挑出标题/简介里带旅行字样的，再按播放量从高到低排，
#      剔掉前端已经展示过的（seen），取前 5 条。
#
# 刷新按钮 = 再打一次这个接口。seen 由前端攒着，所以一直刷新一直有新视频，
# 直到 B 站那一批确实被翻完了，才会允许重复（返回 repeat=true）。
# =====================================================================

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, Request

from .. import bilibili
from ..llm_settings import resolve_llm
from ..providers.deepseek import suggest_vlog_keywords

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vlog", tags=["vlog"])


@router.get("/play")
async def play(bvid: str = Query(..., min_length=6, max_length=20, description="B站视频号，如 BV1xx...")):
    """给浮窗播放器要一个 mp4 直链（比 iframe 干净：没有「进入哔哩哔哩」引导按钮）"""
    try:
        info = await bilibili.video_stream_info(bvid)
    except bilibili.BiliUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "bvid": bvid,
        "url": info["url"],
        "backup": info.get("backup") or [],
        "quality": info.get("quality") or 0,
        "duration_ms": info.get("duration_ms") or 0,
    }

# 标题 / 简介里出现这些词，才算「旅行视频」。
# 主要是为了把 B 站上一堆以城市名命名的歌曲、指弹教程挡在外面：
# 搜「成都 旅行vlog」时它们播放量往往很高，不挡就会霸屏。
TRAVEL_WORDS = (
    "vlog",
    "旅行",
    "旅游",
    "攻略",
    "游记",
    "打卡",
    "游玩",
    "逛",
    "citywalk",
    "徒步",
    "自驾",
    "一日游",
    "旅行记",
    "旅拍",
)


def _looks_like_travel(video: dict, region: str) -> bool:
    """标题或简介里既要有地区名，也要有旅行相关的词"""
    text = f'{video.get("title") or ""} {video.get("description") or ""}'.lower()
    if region and region.lower() not in text:
        return False
    return any(word in text for word in TRAVEL_WORDS)


@router.get("/recommend")
async def recommend(
    request: Request,
    region: str = Query("", max_length=40, description="地区 / 城市 / 景区"),
    q: str = Query("", max_length=40, description="手动搜索关键词（给了就忽略 region）"),
    kind: str = Query("video", pattern="^(video|up)$", description="video=按标题搜视频，up=按 UP 主搜"),
    seen: str = Query("", max_length=900, description="已经展示过的 bvid，逗号分隔"),
    limit: int = Query(5, ge=1, le=10),
):
    query = (q or "").strip()
    # 搜索模式：用户自己在搜索框里敲的词，直接当关键词用，不做旅行词过滤
    # （不然搜「重庆火锅」「海边日落」这种会被过滤空）
    search_mode = bool(query)
    up_mode = search_mode and kind == "up"
    name = query or (region or "").strip() or "青岛"

    # ---- ① 想搜索词 ----
    # 按地区推荐 / 按标题搜：让模型改写成更像真人敲的搜索词；
    # 按 UP 主搜：不用改词，但会先搜一次「UP 主」拿到确切名字。
    llm = resolve_llm(request)
    keywords: list[str] = []
    llm_error = ""
    matched_users: list[dict] = []

    if up_mode:
        matched_users = await bilibili.search_users(name, limit=3)
        if not matched_users:
            # 一个 UP 主都没匹配上：直接说清楚，别退回去搜视频
            # （不然「CF加班v发给…」这种输入会捞一堆标题带 CF 的无关视频）
            raise HTTPException(
                status_code=404,
                detail=f"没找到叫「{name}」的 UP 主，换个准确的名字试试（比如全名或 B 站 ID）",
            )
        # 用 mid 直接拉这个 UP 的投稿列表：这才是「TA 发的视频」
        primary = matched_users[0]
        keywords = [primary["uname"]]
        try:
            videos = await bilibili.user_videos(
                primary["mid"], limit=30, order="pubdate", avatar=primary["avatar"]
            )
        except bilibili.BiliUnavailable as exc:
            # 投稿列表被风控/签名挂了：退回「按名字搜视频 + 作者名严格匹配」
            logger.warning("[vlog] 取投稿列表失败，退回首搜：%s", exc)
            try:
                fallback = await bilibili.search_videos(primary["uname"], order="totalrank")
            except bilibili.BiliUnavailable as exc2:
                raise HTTPException(status_code=503, detail=str(exc2)) from exc2
            wanted = primary["uname"].strip().lower()
            videos = [
                video
                for video in fallback
                if (video.get("author") or "").strip().lower() == wanted
            ]
            if not videos:
                # 搜不到 TA 的视频：多半是 space 接口被限流（412），不是"没这个人"
                cooldown = "过一两分钟再点一次"
                raise HTTPException(
                    status_code=503,
                    detail=f"取不到「{primary['uname']}」的投稿（B站限流：{exc}），{cooldown}",
                ) from exc
        if not videos:
            raise HTTPException(
                status_code=404,
                detail=f"「{primary['uname']}」名下没有能展示的视频（可能都是番剧/付费内容）",
            )
    else:
        if llm["api_key"]:
            try:
                keywords = await suggest_vlog_keywords(
                    name,
                    api_key=llm["api_key"],
                    base_url=llm["base_url"],
                    model=llm["model"],
                )
            except Exception as exc:      # 想词失败不该让整个面板空着
                llm_error = str(exc)
                logger.warning("[vlog] 生成搜索词失败：%s", exc)
        if not keywords:
            if search_mode:
                # 搜索模式：用户敲的原词 + 两个变体，别硬塞「旅行vlog」
                keywords = [name, f"{name} vlog", f"{name} 推荐"]
            else:
                keywords = [f"{name} 旅行vlog", f"{name} 旅游攻略", f"{name} 一日游vlog"]

    # ---- ② 搜 B 站：统一按「综合」排 ----
    # 别用 order="click"（按播放量排）：搜「成都 旅行vlog」会直接跑偏到
    # 赵雷的《成都》录音棚版、《成都》指弹教程这种高播放音乐视频。
    # 综合排序先保证相关性，播放量高低下一步在合并池里自己排。
    if up_mode:
        # 上面已经用投稿列表拿到了 videos，不用再搜
        pool: dict[str, dict] = {}
        errors: list[str] = []
    else:
        tasks = [bilibili.search_videos(word, order="totalrank") for word in keywords[:4]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        pool = {}
        errors = []
        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
                continue
            for video in result:
                pool.setdefault(video["bvid"], video)

        if not pool:
            # 一条都没搜到：把 B 站的原因直接告诉前端，别显示成"这里什么都没有"
            raise HTTPException(status_code=503, detail=errors[0] if errors else "没有搜到相关视频")

    # ---- ③ 排序 / 过滤 ----
    if up_mode:
        # videos 已经是这个 UP 主的投稿列表（按发布时间倒序），不用再排
        pass
    elif search_mode:
        # 搜索模式：用户可能想看的是美食、风景、攻略
        # 所以不筛「旅行」，也【不按播放量重排】——按 B 站综合排序的相关度来，
        # 谁跟关键词更贴谁在前，播放量只是个参考数字显示在卡片上
        videos = list(pool.values())
    else:
        travel = [video for video in pool.values() if _looks_like_travel(video, name)]
        # 播放量降序；「真旅行视频」整体排在前面，剩下的兜底垫底（免得一条不剩）
        travel.sort(key=lambda item: item.get("play") or 0, reverse=True)
        travel_ids = {video["bvid"] for video in travel}
        others = [video for video in pool.values() if video["bvid"] not in travel_ids]
        others.sort(key=lambda item: item.get("play") or 0, reverse=True)
        videos = travel + others

    seen_set = {piece.strip() for piece in (seen or "").split(",") if piece.strip()}
    fresh = [video for video in videos if video["bvid"] not in seen_set]

    repeat = False
    if not fresh:
        # 这批已经全看过了：允许重复，否则点刷新就一片空白
        fresh = videos
        repeat = True

    return {
        "region": name,
        "mode": "search" if search_mode else "region",
        "kind": "up" if up_mode else "video",
        "keywords": keywords,
        "users": matched_users,
        "videos": fresh[:limit],
        "repeat": repeat,
        "error": llm_error,
    }
