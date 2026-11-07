# =====================================================================
# routers/trains.py —— 动车/高铁班次查询
#   GET /api/trains?from=三明北&to=福州&date=2026-11-10
#   数据来自 12306 余票查询（server/train_check.py），需要登录。
# =====================================================================

from fastapi import APIRouter, Depends, HTTPException, Query

from ..train_check import TrainError, fetch_trains
from .auth import current_user

router = APIRouter(prefix="/api/trains", tags=["trains"])


@router.get("")
async def get_trains(
    from_station: str = Query(..., alias="from", min_length=1, max_length=40),
    to_station: str = Query(..., alias="to", min_length=1, max_length=40),
    date: str | None = Query(default=None, description="YYYY-MM-DD，默认明天"),
    user: dict = Depends(current_user),
):
    try:
        return await fetch_trains(from_station, to_station, date)
    except TrainError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
