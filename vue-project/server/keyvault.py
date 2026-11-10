# =====================================================================
# keyvault.py —— API Key 的落盘保护：加密存储 + 掩码展示
# ---------------------------------------------------------------------
# 为什么不是"哈希"：
#   Key 是凭据，每次调用上游都要原样发出去（Authorization: Bearer xxx）。
#   哈希是单向的——存进去就再也拿不回来，聊天、查余额、语音合成会全部失效。
#   所以这里做的是「可逆加密」：库里只有密文，只有本机进程能解开；
#   接口返回给前端的一律是掩码（sk-ab••••wxyz），日志也不打原文。
#
# 用的算法：Fernet（AES-128-CBC + HMAC-SHA256，自带防篡改）
#   密文格式：enc:v1:<urlsafe-base64 token>
#   前缀有两个作用：一眼能认出"这条已经加密"，以及兼容老库里的明文
#   （读到没有前缀的值就当成明文，下次写入时自动加密）。
#
# 主密钥从哪来（按顺序）：
#   1. 环境变量 FUFU_KEY_SECRET —— 自己给一串口令，内部 SHA-256 派生成 32 字节
#   2. 项目根 .keys/master.key —— 首次运行自动生成，已在 .gitignore 里
#   丢了主密钥 = 库里的 Key 解不开（重新在设置里填一次即可），
#   所以备份数据库时记得把这个文件一起备份。
# =====================================================================

import base64
import hashlib
import os
import sqlite3
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

PREFIX = "enc:v1:"

ROOT = Path(__file__).resolve().parent.parent      # vue-project/
KEY_FILE = ROOT / ".keys" / "master.key"


def _secret_from_env() -> bytes | None:
    raw = (os.environ.get("FUFU_KEY_SECRET") or "").strip()
    if not raw:
        return None
    # 任意口令 → 固定 32 字节；用 sha256 派生，避免长度/字符集限制
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _secret_from_file() -> bytes:
    """读 .keys/master.key；没有就生成一个（首次运行）"""
    if KEY_FILE.exists():
        text = KEY_FILE.read_text(encoding="ascii").strip()
        if text:
            return text.encode("ascii")

    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    KEY_FILE.write_text(key.decode("ascii"), encoding="ascii")
    try:
        os.chmod(KEY_FILE, 0o600)          # Windows 上作用有限，但不会报错
    except OSError:
        pass
    return key


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    secret = _secret_from_env() or _secret_from_file()
    return Fernet(secret)


def is_encrypted(value: str | None) -> bool:
    return bool(value) and str(value).startswith(PREFIX)


def encrypt_text(plain: str | None) -> str:
    """明文 → enc:v1:...；空串保持空串，已加密的原样返回（幂等）"""
    text = (plain or "").strip()
    if not text:
        return ""
    if is_encrypted(text):
        return text
    token = _fernet().encrypt(text.encode("utf-8")).decode("ascii")
    return PREFIX + token


def decrypt_text(stored: str | None) -> str:
    """enc:v1:... → 明文；没有前缀的当成老明文直接返回；解不开返回空串"""
    value = (stored or "").strip()
    if not value:
        return ""
    if not is_encrypted(value):
        return value
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        # 主密钥换了 / 文件损坏：不当成崩溃，让用户重新填一次 Key
        return ""


def fingerprint(plain: str | None) -> str:
    """Key 的短指纹（sha256 前 12 位），用于日志里比对"是不是同一把 Key"，
    不会泄露内容，也不可逆推。"""
    text = (plain or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


# 需要加密的列：(表, 主键列, 列名)
_ENCRYPTED_COLUMNS = (
    ("user_providers", "id", "api_key"),
    ("user_tts_settings", "user_id", "api_key"),
)


def migrate_plaintext(conn: sqlite3.Connection) -> int:
    """启动时跑：把库里残留的明文 Key 逐条加密。返回处理条数。

    幂等：带 enc:v1: 前缀的直接跳过；空值跳过。
    """
    changed = 0
    for table, pk, column in _ENCRYPTED_COLUMNS:
        try:
            rows = conn.execute(
                f"SELECT {pk} AS pk, {column} AS value FROM {table} "
                f"WHERE {column} IS NOT NULL AND {column} <> ''"
            ).fetchall()
        except sqlite3.OperationalError:
            continue                     # 老库没有这张表 / 这一列
        for row in rows:
            value = row["value"]
            if is_encrypted(value):
                continue
            conn.execute(
                f"UPDATE {table} SET {column} = ? WHERE {pk} = ?",
                (encrypt_text(value), row["pk"]),
            )
            changed += 1
    return changed
