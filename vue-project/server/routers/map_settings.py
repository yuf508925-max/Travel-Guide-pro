# =====================================================================
# routers/map_settings.py —— 高德地图 Key（全局写死，一人一份的旧方案已废弃）
#   GET /api/map   返回内置的 Key / 安全密钥
#
# 为什么不再让用户填：
#   这是「Web端 (JS API)」Key，它最终一定要出现在浏览器加载的脚本地址里，
#   不是机密。用户自己填反而容易填错（类型选错、忘了安全密钥），
#   所以直接固定在 server/config.py，换 Key 只改那一处。
#
# 历史：早期存在 user_map_settings 表里按账号保存，现在表还在但不再读写。
# =====================================================================

from fastapi import APIRouter, Depends

from ..config import AMAP_JS_KEY, AMAP_SECURITY_CODE
from .auth import current_user

router = APIRouter(prefix="/api/map", tags=["map"])


@router.get("")
def get_map_settings(user: dict = Depends(current_user)):
    """当前账号拿到的永远是同一份内置 Key（保留登录校验，避免匿名刷接口）"""
    return {
        "amap_key": AMAP_JS_KEY,
        "security_code": AMAP_SECURITY_CODE,
        "updated_at": "",
    }
