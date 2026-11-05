# =====================================================================
# security.py —— 密码哈希 / 校验
#   只用 Python 标准库（hashlib.scrypt），不引第三方库。
#   库里只存 "scrypt$盐$哈希" 这种字符串，绝不存明文。
# =====================================================================

import base64
import hashlib
import hmac
import os

# scrypt 参数：N=2^14 约 16MB 内存、几十毫秒，足够安全也不至于卡顿
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LEN = 32


def hash_password(plain: str) -> str:
    """明文密码 → 可入库的哈希串（每次随机加盐）"""
    salt = os.urandom(16)
    dk = hashlib.scrypt(
        plain.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_LEN,
    )
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(plain: str, stored: str) -> bool:
    """校验明文密码和库里的哈希是否匹配（用 compare_digest 防时序攻击）"""
    try:
        algo, salt_b64, hash_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.scrypt(
            plain.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=len(expected),
        )
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False
