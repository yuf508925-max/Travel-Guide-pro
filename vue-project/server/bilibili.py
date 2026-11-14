# =====================================================================
# bilibili.py —— 搜 B 站视频（旅行 vlog 面板用）
#   用的是 B 站网页版自己的搜索接口：
#     GET https://api.bilibili.com/x/web-interface/search/type
#         ?search_type=video&keyword=青岛旅行vlog&page=1
#   不用登录、不用 Key，只要带一个像浏览器的 UA + Referer。
#
#   两个必须防的坑：
#     ① 频控：短时间请求太多会返回 code=-412（"请求被拦截"），
#        所以这里带一个 5 分钟的进程内缓存，并且把限流翻成人话报给前端；
#     ② 字段会变：B 站是网页接口，个别字段某天就没了——
#        解析一律走 .get() + 兜底，缺字段宁可显示空白也不抛异常。
# =====================================================================

import asyncio
import html
import hashlib
import http.cookiejar
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
HOME_URL = "https://www.bilibili.com/"
REFERER = "https://www.bilibili.com/"
# 不带浏览器 UA 会被直接拦；Referer 也要给，否则风控更严
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
TIMEOUT = 10.0

# 同一个关键词 5 分钟内不重复打 B 站（刷新按钮连点也不会被限流）
CACHE_TTL = 300.0
_cache: dict[str, tuple[float, list[dict]]] = {}

# 搜索结果标题里带 <em class="keyword"> 高亮标签，显示前要去掉
_TAG_RE = re.compile(r"<[^>]+>")

# ---------------------------------------------------------------------
# 关于 412
#   裸着请求搜索接口，几次之后 B 站就会返回 HTTP 412（风控拦了）。
#   解决办法：先用同一个 CookieJar 访问一次首页，拿到 buvid3 / b_nut
#   这两个匿名标识，之后的搜索请求就像正常浏览器了。
#   opener 全程复用，Cookie 也就一直有效。
# ---------------------------------------------------------------------
_opener_lock = threading.Lock()
_opener: urllib.request.OpenerDirector | None = None
_seeded_at = 0.0
SEED_TTL = 1800.0


def _build_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _get_opener(force_seed: bool = False) -> urllib.request.OpenerDirector:
    """拿一个带 Cookie 的 opener；首次（或过期）先访问首页播种 Cookie"""
    global _opener, _seeded_at
    with _opener_lock:
        if _opener is None:
            _opener = _build_opener()
        if force_seed or time.time() - _seeded_at > SEED_TTL:
            try:
                _opener.open(
                    urllib.request.Request(HOME_URL, headers={"User-Agent": USER_AGENT}),
                    timeout=TIMEOUT,
                ).read()
                _seeded_at = time.time()
            except Exception:  # noqa: BLE001 - 播种失败也继续试，说不定刚好能用
                _seeded_at = time.time() - SEED_TTL + 60
        return _opener


class BiliUnavailable(Exception):
    """B 站接口不可用（超时 / 限流 / 返回格式不对）"""


def _clean_text(raw) -> str:
    """去 HTML 高亮标签、反转义 &amp; 这类实体"""
    return html.unescape(_TAG_RE.sub("", str(raw or ""))).strip()


def _secure_url(raw) -> str:
    """封面 / 头像经常是 //i0.hdslb.com/... 这种协议相对地址"""
    url = str(raw or "").strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://"):
        return "https://" + url[len("http://"):]
    return url


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _fetch_once_sync(params: dict, force_seed: bool = False) -> bytes:
    """真正发一次请求，返回原始字节；412 抛 HTTPError 由上层决定要不要重试"""
    url = f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": REFERER,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    opener = _get_opener(force_seed=force_seed)
    with opener.open(request, timeout=TIMEOUT) as response:
        return response.read()


def _fetch_sync(params: dict) -> dict:
    """同步请求一次（放到线程里跑，别堵事件循环）"""
    try:
        payload = _fetch_once_sync(params)
    except urllib.error.HTTPError as exc:
        if exc.code in (412, 403):
            # 大概率是 Cookie 失效了：重新播种一次再试一把
            try:
                payload = _fetch_once_sync(params, force_seed=True)
            except urllib.error.HTTPError as retry_exc:
                if retry_exc.code in (412, 403):
                    raise BiliUnavailable("B站暂时拦住了这次搜索，等几秒再点刷新") from retry_exc
                raise BiliUnavailable(f"B站搜索返回了 {retry_exc.code}") from retry_exc
        else:
            raise BiliUnavailable(f"B站搜索返回了 {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BiliUnavailable("连不上B站，检查一下网络") from exc

    try:
        data = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BiliUnavailable("B站返回的数据看不懂") from exc

    code = data.get("code")
    if code == -412:
        raise BiliUnavailable("B站限流了，等几秒再点刷新")
    if code != 0:
        raise BiliUnavailable(f"B站没给结果（code {code}）")
    return data.get("data") or {}


def _parse_item(item: dict) -> dict | None:
    """搜索结果里的一条 → 前端好用的结构；缺 bvid 的直接丢掉"""
    bvid = str(item.get("bvid") or "").strip()
    if not bvid:
        return None
    title = _clean_text(item.get("title"))
    if not title:
        return None
    return {
        "bvid": bvid,
        "title": title,
        "cover": _secure_url(item.get("pic")),
        "author": _clean_text(item.get("author")),
        "author_avatar": _secure_url(item.get("upic")),
        "play": _as_int(item.get("play")),
        "danmaku": _as_int(item.get("video_review")),
        # "12:34" 这种时长，直接用
        "duration": str(item.get("duration") or ""),
        "pubdate": _as_int(item.get("pubdate")),
        "description": _clean_text(item.get("description"))[:160],
        "url": f"https://www.bilibili.com/video/{bvid}",
    }


async def search_videos(keyword: str, page: int = 1, order: str = "totalrank") -> list[dict]:
    """按关键词搜视频，返回最多 ~20 条（B 站一页就是 20 条）

    order：
        totalrank = 综合排序（默认，相关度优先）
        click     = 按播放量排序（只有「按地区推荐」才用，搜索结果太容易跑偏）
    """
    word = (keyword or "").strip()
    if not word:
        return []

    cache_key = f"{order}|{word}"
    cached = _cache.get(cache_key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]

    data = await asyncio.to_thread(
        _fetch_sync,
        {"search_type": "video", "keyword": word, "page": page, "order": order},
    )
    videos = []
    for item in data.get("result") or []:
        parsed = _parse_item(item)
        if parsed:
            videos.append(parsed)

    _cache[cache_key] = (time.time(), videos)
    return videos


def clear_cache() -> None:
    """调试用：强制下次真的去打 B 站"""
    _cache.clear()


# =====================================================================
# 搜 UP 主 + 取这个 UP 主的投稿列表
# ---------------------------------------------------------------------
# 「按 UP 主搜」有两套 API：
#   ① /x/space/wbi/arc/search —— 正经的「这个 UP 的投稿列表」，
#      必须带 wbi 签名（w_rid = md5(排序后的query + mixinKey)），
#      mixinKey 由 /x/web-interface/nav 返回的 img_url / sub_url 重排得来；
#   ② 退一步：先搜「UP 主」（search_type=bili_user）拿到名字，
#      再按名字搜视频、只用 author 跟名字对得上的那几条 —— 不准
#      （搜「CF加班…」这种输入会捞回一堆标题里含 CF 的无关视频）。
# 现在用 ①：拿 mid 直接拉投稿，结果是「这个 UP 发的」而不是「跟这词有关的」，
# 精准度完全不同。签名算法万一变了，_user_videos_sync 会抛 BiliUnavailable，
# 上层再退回 ② 的按名字搜。
# =====================================================================

SPACE_ARC_URL = "https://api.bilibili.com/x/space/wbi/arc/search"
APP_SPACE_URL = "https://app.bilibili.com/x/v2/space/archive/cursor"
APP_KEY = "1d8b6e7d45233436"
APP_SECRET = "560c52ccd288fed045859ed18bffd973"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
USER_SEARCH_TTL = 600.0
_user_cache: dict[str, tuple[float, list[dict]]] = {}

# 投稿列表的缓存 + 「被风控了先歇一会儿」
USER_VIDEOS_TTL = 900.0
SPACE_COOLDOWN = 120.0
_user_videos_cache: dict[str, tuple[float, list[dict]]] = {}
_space_blocked_until: float = 0.0

# wbi 的字符重排表（B 站前端 hardcode 的那张）
_MIXIN_KEY_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

_mixin_key: str = ""
_mixin_key_at: float = 0.0
MIXIN_KEY_TTL = 3600.0


def _key_from_url(url: str) -> str:
    return (url or "").rsplit("/", 1)[-1].split(".")[0]


def _nav_json_sync() -> dict:
    """裸取 nav（未登录会返回 code=-101，但 data.wbi_img 照样有）"""
    request = urllib.request.Request(
        NAV_URL,
        headers={"User-Agent": USER_AGENT, "Referer": REFERER},
    )
    with _get_opener().open(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_mixin_key(force: bool = False) -> str:
    global _mixin_key, _mixin_key_at
    if not force and _mixin_key and time.time() - _mixin_key_at < MIXIN_KEY_TTL:
        return _mixin_key
    try:
        nav = _nav_json_sync()
        wbi = (nav.get("data") or {}).get("wbi_img") or {}
        raw = _key_from_url(wbi.get("img_url")) + _key_from_url(wbi.get("sub_url"))
        if len(raw) < 64:
            raise ValueError("nav 没给 wbi_img")
        _mixin_key = "".join(raw[i] for i in _MIXIN_KEY_TAB)[:32]
        _mixin_key_at = time.time()
        return _mixin_key
    except Exception:
        # 拿不到新 key 就先用旧的（过期的 key 至少还能试一次）
        return _mixin_key


def _sign_wbi(params: dict) -> dict:
    mixin = _get_mixin_key()
    if not mixin:
        raise BiliUnavailable("B站签名参数没拿到，稍后再试")
    signed = {k: v for k, v in params.items() if v is not None}
    signed["wts"] = int(time.time())
    query = urllib.parse.urlencode(sorted(signed.items()))
    signed["w_rid"] = hashlib.md5((query + mixin).encode("utf-8")).hexdigest()
    return signed


def _space_json_sync(params: dict, force_key: bool = False) -> dict:
    if force_key:
        _get_mixin_key(force=True)
    signed = _sign_wbi(params)
    url = SPACE_ARC_URL + "?" + urllib.parse.urlencode(signed)
    mid = signed.get("mid") or 0
    # Referer 必须指到这个 UP 的「投稿」页、再带上 Origin：
    # 只给首页 Referer 时，B 站 10 次里有 8 次返回 code -352（风控校验失败），
    # 换成空间页 Referer 后实测稳定 code 0。这一步踩过坑，别删。
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": f"https://space.bilibili.com/{mid}/video",
            "Origin": "https://space.bilibili.com",
            "Accept": "application/json, text/plain, */*",
        },
    )
    try:
        with _get_opener().open(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise BiliUnavailable(f"B站暂时拦住了这次请求（HTTP {exc.code}）") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BiliUnavailable("B站连不上，检查一下网络") from exc


def _parse_space_item(item: dict, avatar: str = "") -> dict | None:
    """space 投稿列表里的一条（字段名和搜索接口不一样）"""
    bvid = str(item.get("bvid") or "").strip()
    title = _clean_text(item.get("title"))
    if not bvid or not title:
        return None
    return {
        "bvid": bvid,
        "title": title,
        "cover": _secure_url(item.get("pic")),
        "author": _clean_text(item.get("author")),
        "author_avatar": avatar,
        "play": _as_int(item.get("play")),
        "danmaku": _as_int(item.get("video_review")),
        # space 里的时长字段叫 length，是 "12:34" 这种字符串
        "duration": str(item.get("length") or ""),
        "pubdate": _as_int(item.get("created")),
        "description": _clean_text(item.get("description"))[:160],
        "url": f"https://www.bilibili.com/video/{bvid}",
    }


def _app_json_sync(params: dict) -> dict:
    """APP 端的接口（appkey + md5 签名），PC 端被 412 时它往往还活着"""
    query = dict(params)
    query["appkey"] = APP_KEY
    query["build"] = 7680300
    query["mobi_app"] = "iphone"
    query["platform"] = "ios"
    query["ts"] = int(time.time())
    query["sign"] = hashlib.md5(
        (urllib.parse.urlencode(sorted(query.items())) + APP_SECRET).encode("utf-8")
    ).hexdigest()
    url = APP_SPACE_URL + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Referer": REFERER},
    )
    try:
        with _get_opener().open(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise BiliUnavailable(f"B站暂时拦住了这次请求（HTTP {exc.code}）") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BiliUnavailable("B站连不上，检查一下网络") from exc


def _fmt_duration(seconds) -> str:
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return ""
    if total <= 0:
        return ""
    return f"{total // 60}:{total % 60:02d}"


def _parse_app_item(item: dict, avatar: str = "") -> dict | None:
    """APP 投稿列表里的一条"""
    bvid = str(item.get("bvid") or "").strip()
    title = _clean_text(item.get("title"))
    if not bvid or not title:
        return None
    return {
        "bvid": bvid,
        "title": title,
        "cover": _secure_url(item.get("cover")),
        "author": _clean_text(item.get("author")),
        "author_avatar": avatar,
        "play": _as_int(item.get("play")),
        "danmaku": _as_int(item.get("danmaku")),
        "duration": _fmt_duration(item.get("duration")),
        "pubdate": _as_int(item.get("ctime")),
        "description": _clean_text(item.get("desc"))[:160],
        "url": f"https://www.bilibili.com/video/{bvid}",
    }


def _app_user_videos_sync(mid: int, limit: int, order: str, avatar: str) -> list[dict]:
    collected: list[dict] = []
    cursor = 0
    for _ in range(3):
        params = {"vmid": mid, "ps": 20, "order": order}
        if cursor:
            params["next"] = cursor
        data = _app_json_sync(params)
        if data.get("code") != 0:
            raise BiliUnavailable(f"取不到这个 UP 主的投稿（code {data.get('code')}）")
        payload = data.get("data") or {}
        for item in payload.get("item") or []:
            parsed = _parse_app_item(item, avatar)
            if parsed:
                collected.append(parsed)
        cursor = payload.get("next_cursor") or 0
        if len(collected) >= limit or not payload.get("has_next") or not cursor:
            break
    return collected[:limit]


def _space_user_videos_sync(mid: int, limit: int, order: str, avatar: str) -> list[dict]:
    page = 1
    collected: list[dict] = []
    while len(collected) < limit and page <= 3:
        data = _space_json_sync({"mid": mid, "ps": 50, "pn": page, "order": order})
        code = data.get("code")
        if code != 0:
            # -403/-352 大多是 wbi 签名被拒：换一把 mixinKey 再试一次。
            # 注意 HTTP 412（真限流）在 _space_json_sync 里已经抛成 BiliUnavailable 了，
            # 不走这里——限流时立刻重试只会把封锁时间拖得更长。
            if page == 1 and code in (-403, -352, -311):
                data = _space_json_sync(
                    {"mid": mid, "ps": 50, "pn": page, "order": order},
                    force_key=True,
                )
                if data.get("code") != 0:
                    raise BiliUnavailable(f"取不到这个 UP 主的投稿（code {data.get('code')}）") from None
            elif page == 1:
                raise BiliUnavailable(f"取不到这个 UP 主的投稿（code {code}）") from None
            else:
                break
        vlist = ((data.get("data") or {}).get("list") or {}).get("vlist") or []
        for item in vlist:
            parsed = _parse_space_item(item, avatar)
            if parsed:
                collected.append(parsed)
        if len(vlist) < 50:
            break
        page += 1
    return collected[:limit]


async def user_videos(mid: int, limit: int = 30, order: str = "pubdate", avatar: str = "") -> list[dict]:
    """某个 UP 主的投稿（order: pubdate 最新 / click 播放量 / stow 收藏）

    顺序：APP 接口（稳、不常被拦）→ PC 的 wbi 接口（会被 412 限流）→ 抛 BiliUnavailable
    让上层走「按名字搜 + 作者名严格匹配」的退路。
    """
    if not mid:
        return []

    cache_key = f"{mid}|{order}|{limit}"
    cached = _user_videos_cache.get(cache_key)
    if cached and time.time() - cached[0] < USER_VIDEOS_TTL:
        return cached[1]

    global _space_blocked_until
    try:
        videos = await asyncio.to_thread(
            _app_user_videos_sync, int(mid), limit, order, avatar
        )
    except BiliUnavailable as app_error:
        if _space_blocked_until > time.time():
            raise BiliUnavailable(
                "B站拦了投稿列表，过一两分钟再试"
            ) from app_error
        try:
            videos = await asyncio.to_thread(
                _space_user_videos_sync, int(mid), limit, order, avatar
            )
        except BiliUnavailable as exc:
            _space_blocked_until = time.time() + SPACE_COOLDOWN
            raise exc from None

    _user_videos_cache[cache_key] = (time.time(), videos)
    return videos


def _parse_user(item: dict) -> dict | None:
    """搜索结果里的一个 UP 主"""
    mid = _as_int(item.get("mid"))
    uname = _clean_text(item.get("uname"))
    if not mid or not uname:
        return None
    return {
        "mid": mid,
        "uname": uname,
        "avatar": _secure_url(item.get("upic")),
        "sign": _clean_text(item.get("usign"))[:80],
        "fans": _as_int(item.get("fans")),
        "videos": _as_int(item.get("videos")),
        "url": f"https://space.bilibili.com/{mid}",
    }


async def search_users(keyword: str, limit: int = 3) -> list[dict]:
    """按关键词搜 UP 主，返回最多 limit 个（按综合排序）"""
    word = (keyword or "").strip()
    if not word:
        return []

    cached = _user_cache.get(word)
    if cached and time.time() - cached[0] < USER_SEARCH_TTL:
        return cached[1][:limit]

    try:
        data = await asyncio.to_thread(
            _fetch_sync,
            {"search_type": "bili_user", "keyword": word, "page": 1},
        )
    except BiliUnavailable:
        # 搜 UP 主失败不该让整个搜索失败：上层会退回「按名字搜视频」
        return []

    users = []
    for item in data.get("result") or []:
        parsed = _parse_user(item)
        if parsed:
            users.append(parsed)

    _user_cache[word] = (time.time(), users)
    return users[:limit]


# =====================================================================
# 取视频的直链（给浮窗里的 <video> 用）
# ---------------------------------------------------------------------
# 为什么不用 player.bilibili.com 那个 iframe：
#   外链播放器会在画面里糊一个「进入哔哩哔哩，观看更高清」的引导按钮，
#   那个按钮在跨域 iframe 里，外面既改不了 CSS 也删不掉。
#   改成自己拿 mp4 直链塞进 <video>，播放器是我们自己的，画面上就干净了。
#
# 代价：playurl 里 platform=html5 走的是「未登录」档，只有 360P
#   （qn=64 会降成 16）。想上 1080P 得带登录 Cookie，这里不做。
# =====================================================================

VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
PLAYURL_URL = "https://api.bilibili.com/x/player/playurl"
# 直链有时效（一般 2 小时左右），这里缓存 20 分钟就够用了
PLAY_CACHE_TTL = 1200.0
_play_cache: dict[str, tuple[float, dict]] = {}


def _api_json_sync(url: str, params: dict) -> dict:
    """调 api.bilibili.com 上的普通 JSON 接口（同样复用带 Cookie 的 opener）"""
    full = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        full,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": REFERER,
            "Accept": "application/json, text/plain, */*",
        },
    )
    opener = _get_opener()
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise BiliUnavailable("B站暂时拦住了这次请求，等几秒再试") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BiliUnavailable("连不上B站，检查一下网络") from exc

    try:
        data = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BiliUnavailable("B站返回的数据看不懂") from exc

    if data.get("code") != 0:
        raise BiliUnavailable(f"B站没给播放地址（code {data.get('code')}）")
    return data.get("data") or {}


def _play_info_sync(bvid: str) -> dict:
    """bvid → mp4 直链 + 清晰度"""
    view = _api_json_sync(VIEW_URL, {"bvid": bvid})
    cid = view.get("cid")
    if not cid:
        raise BiliUnavailable("拿不到这个视频的分P信息")

    play = _api_json_sync(
        PLAYURL_URL,
        {
            "bvid": bvid,
            "cid": cid,
            "qn": "64",
            "fnval": "1",     # 1 = mp4/flv 直链（不要 DASH，省得音视频分离）
            "fnver": "0",
            "fourk": "0",
            "platform": "html5",
            "high_quality": "1",
        },
    )
    durl = play.get("durl") or []
    if not durl:
        raise BiliUnavailable("这个视频没有可直链播放的格式")

    first = durl[0]
    return {
        "url": str(first.get("url") or ""),
        "quality": _as_int(play.get("quality")),
        "size": _as_int(first.get("size")),
        # durl 里给的是时长（毫秒），前端可用来显示进度
        "duration_ms": _as_int(first.get("length")),
        "backup": [str(item.get("url") or "") for item in (first.get("backup_url") or [])],
    }


async def video_stream_info(bvid: str) -> dict:
    """按 bvid 拿可直链播放的 mp4 地址（20 分钟内复用）"""
    key = (bvid or "").strip()
    if not key:
        raise BiliUnavailable("没给视频号")

    cached = _play_cache.get(key)
    if cached and time.time() - cached[0] < PLAY_CACHE_TTL:
        return cached[1]

    info = await asyncio.to_thread(_play_info_sync, key)
    if not info.get("url"):
        raise BiliUnavailable("B站没返回播放地址")
    _play_cache[key] = (time.time(), info)
    return info
