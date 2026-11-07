# =====================================================================
# train_check.py —— 查动车/高铁班次（数据来自 12306 余票查询）
# ---------------------------------------------------------------------
# 高德的 Transfer 只做市内公交，跨城时给不到真实动车班次，
# 所以这里直接走 12306 的公开查询接口：
#   1. station_name.js  拿车站名 → 电码（带缓存）
#   2. leftTicket/init  取一个 Cookie（12306 对无 Cookie 的请求会拒）
#   3. leftTicket/queryZ 查某天余票，返回 | 分隔的字符串数组
#
# 注意：
#   · 12306 的证书链在部分 Python 里校验失败，这里用 truststore 走系统证书库
#   · 这是网页接口不是官方开放 API，字段位置可能变；解析做了长度保护
#   · 只返回车次/时间/历时/余票，不猜票价（票价要另一个接口，容易不准）
# =====================================================================

import asyncio
import datetime as dt
import json
import re
import urllib.error
import urllib.parse
import urllib.request

try:
    # 让 Python 用 Windows 自带的证书库，否则 12306 会报 CERTIFICATE_VERIFY_FAILED
    import truststore

    truststore.inject_into_ssl()
except Exception:  # 没装也不至于起不来，只是可能证书校验失败
    pass

BASE = "https://kyfw.12306.cn"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
TIMEOUT = 12.0
MAX_AHEAD_DAYS = 14


class TrainError(Exception):
    """查询失败（车站没找到 / 日期不合法 / 12306 连不上）"""


_stations: dict[str, str] = {}      # 站名 → 电码
_station_names: dict[str, str] = {} # 电码 → 站名


def _get(url: str, cookie: str = "") -> tuple[str, list[str]]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Cookie": cookie,
            "Accept": "*/*",
            "Referer": BASE + "/otn/leftTicket/init",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read().decode("utf-8", "replace"), (
                response.headers.get_all("Set-Cookie") or []
            )
    except urllib.error.HTTPError as exc:
        raise TrainError(f"12306 返回 HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TrainError("连不上 12306，检查一下网络") from exc


def _load_stations() -> dict[str, str]:
    global _stations, _station_names
    if _stations:
        return _stations

    js, _ = _get(BASE + "/otn/resources/js/framework/station_name.js")
    stations: dict[str, str] = {}
    names: dict[str, str] = {}
    for match in re.finditer(r"@[a-z]+\|([^|]+)\|([A-Z]+)\|", js):
        name, code = match.group(1), match.group(2)
        stations[name] = code
        names[code] = name

    if not stations:
        raise TrainError("12306 车站列表解析失败")
    _stations, _station_names = stations, names
    return stations


# 城市名后面常见的行政后缀，去掉之后才可能对上车站名
_CITY_SUFFIXES = ("自治州", "自治区", "地区", "特别行政区", "市", "县", "区", "盟")


def _strip_area(name: str) -> str:
    """「三明市」→「三明」；「三明北站」→「三明北」"""
    base = name.strip()
    if base.endswith(("火车站", "高铁站")):
        base = base[: -3]
    elif base.endswith("站"):
        base = base[:-1]

    for suffix in _CITY_SUFFIXES:
        if base.endswith(suffix) and len(base) > len(suffix):
            return base[: -len(suffix)]
    return base


def _resolve_station(name: str) -> str | None:
    """把「三明」「三明市」「三明站」「三明北站」都解析成电码"""
    raw = (name or "").strip()
    if not raw:
        return None

    base = _strip_area(raw)
    stations = _load_stations()

    # 1) 精确：三明 / 三明北
    for candidate in (base, raw):
        if candidate in stations:
            return stations[candidate]

    # 2) 加方位后缀：三明 → 三明北
    for suffix in ("", "东", "西", "南", "北"):
        if base + suffix in stations:
            return stations[base + suffix]

    # 3) 前缀优先（「三明」优先配「三明北」而不是「…三明…」这种）
    for station_name, code in stations.items():
        if base and station_name.startswith(base):
            return code

    for station_name, code in stations.items():
        if base and base in station_name:
            return code
    return None


def city_stations(city: str) -> list[str]:
    """「三明」→ [三明, 三明北]；「福州」→ [福州, 福州南]"""
    base = _strip_area(city)
    if not base:
        return []

    stations = _load_stations()

    # 「福州南」这种已经带方位字的：如果去掉方位字还是个车站（福州），
    # 就把同城的站都列出来，方便在 福州 / 福州南 之间切换。
    bases = [base]
    if len(base) > 2 and base[-1] in "东西南北" and base[:-1] in stations:
        bases.insert(0, base[:-1])

    names = [name for name in stations if any(name.startswith(b) for b in bases)]

    def sort_key(name: str) -> tuple:
        # 完全同名优先，其次按 北/东/南/西 的顺序，最后按名字长短
        if name == base:
            return (0, 0, len(name), name)
        order = {"北": 1, "东": 2, "南": 3, "西": 4}
        return (1, order.get(name[len(base):][:1], 9), len(name), name)

    return sorted(set(names), key=sort_key)[:10]


def _classify(code: str) -> str:
    first = (code or "")[:1].upper()
    return {"G": "高铁", "D": "动车", "C": "城际"}.get(first, "普速")


def _query_sync(from_name: str, to_name: str, date: str | None = None) -> dict:
    today = dt.date.today()
    if date:
        try:
            day = dt.date.fromisoformat(date)
        except ValueError:
            raise TrainError("日期格式要 YYYY-MM-DD") from None
    else:
        day = today + dt.timedelta(days=1)

    if day < today:
        raise TrainError("日期不能早于今天")
    if day > today + dt.timedelta(days=MAX_AHEAD_DAYS):
        raise TrainError(f"12306 只预售 {MAX_AHEAD_DAYS + 1} 天内的车票")

    from_code = _resolve_station(from_name)
    to_code = _resolve_station(to_name)
    if not from_code:
        raise TrainError(f"12306 里没找到车站「{from_name}」")
    if not to_code:
        raise TrainError(f"12306 里没找到车站「{to_name}」")

    _, cookies = _get(BASE + "/otn/leftTicket/init")
    cookie = "; ".join(c.split(";")[0] for c in cookies)

    query = urllib.parse.urlencode(
        {
            "leftTicketDTO.train_date": day.isoformat(),
            "leftTicketDTO.from_station": from_code,
            "leftTicketDTO.to_station": to_code,
            "purpose_codes": "ADULT",
        }
    )
    raw, _ = _get(BASE + "/otn/leftTicket/queryZ?" + query, cookie)

    try:
        data = json.loads(raw)
    except ValueError:
        raise TrainError("12306 返回的数据看不懂，稍后再试") from None

    rows = (data.get("data") or {}).get("result") or []
    trains: list[dict] = []
    for line in rows:
        parts = line.split("|")
        if len(parts) < 11:
            continue
        code = parts[3]
        if not code:
            continue

        # 12306 会按「同城车站组」返回，比如查 三明北→福州 时夹带
        # 三明→福州南 的车次；这里只保留真正经过所选这两个站的车。
        if parts[6] != from_code or parts[7] != to_code:
            continue

        trains.append(
            {
                "code": code,
                "kind": _classify(code),
                "from_station": _station_names.get(parts[6], from_name),
                "to_station": _station_names.get(parts[7], to_name),
                "depart": parts[8],
                "arrive": parts[9],
                "duration": parts[10],
                # 余票字段位置偶尔变，取不到就给空字符串
                "wuzuo": parts[26] if len(parts) > 26 else "",
                "second": parts[30] if len(parts) > 30 else "",
                "first": parts[31] if len(parts) > 31 else "",
                "business": parts[32] if len(parts) > 32 else "",
            }
        )

    # 动车/高铁/城际排前面，同类按出发时间
    trains.sort(key=lambda t: (0 if t["kind"] != "普速" else 1, t["depart"]))
    return {
        "date": day.isoformat(),
        "from": from_name,
        "to": to_name,
        # 实际匹配到的 12306 车站名，前端展示出来避免"城市 vs 车站"的误解
        "from_station": _station_names.get(from_code, from_name),
        "to_station": _station_names.get(to_code, to_name),
        # 该城市所有可选车站（前端做成下拉，方便换到北站/南站）
        "from_options": city_stations(from_name),
        "to_options": city_stations(to_name),
        "total": len(trains),
        "trains": trains[:15],
    }


async def fetch_trains(from_name: str, to_name: str, date: str | None = None) -> dict:
    return await asyncio.to_thread(_query_sync, from_name, to_name, date)
