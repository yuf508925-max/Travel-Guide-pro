# =====================================================================
# music_store.py —— 用户上传音乐的临时文件管理
# ---------------------------------------------------------------------
#   目录结构：server/tmp_music/<登录会话 token>/<随机文件名>.<后缀>
#
#   为什么按「登录会话」而不是按用户放：
#     · 需求是「退出登录就清空这个人的文件夹」，一个 token 正好是一次登录；
#     · 同一账号在别的浏览器/设备上的音乐互不影响；
#     · 会话过期被 sessions 表清掉时，能一眼看出哪些目录该跟着删。
#
#   清理时机（两处，都调这里的函数）：
#     1. 退出登录 → purge_session()：删库里的行 + 删整个目录
#     2. 启动时 init_db() → cleanup_orphans()：会话已经没了的目录/行一起删
# =====================================================================

import shutil
import sqlite3
import uuid
from pathlib import Path

# 临时目录（.gitignore 里已忽略 tmp_music）
MUSIC_ROOT = Path(__file__).parent / "tmp_music"

# 只收这些后缀；其余一律拒绝，避免有人往临时目录塞别的东西
ALLOWED_EXT = {
    ".mp3",
    ".wav",
    ".ogg",
    ".oga",
    ".m4a",
    ".aac",
    ".flac",
    ".opus",
    ".weba",
    ".webm",
}

MAX_BYTES = 40 * 1024 * 1024          # 单首上限 40MB

MUSIC_TABLE = """
CREATE TABLE IF NOT EXISTS music_tracks (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_token TEXT    NOT NULL,
  name          TEXT    NOT NULL DEFAULT '',
  filename      TEXT    NOT NULL,
  ext           TEXT    NOT NULL DEFAULT '',
  size          INTEGER NOT NULL DEFAULT 0,
  position      INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_music_session ON music_tracks(session_token, position);
CREATE INDEX IF NOT EXISTS idx_music_user ON music_tracks(user_id);
"""


def session_dir(token: str) -> Path:
    """某次登录的专属目录（不会自动创建）"""
    # token 是 token_urlsafe 生成的，理论上只有 [A-Za-z0-9_-]，
    # 这里再兜一层，防止拼出 ../ 这种路径
    safe = "".join(ch for ch in token if ch.isalnum() or ch in "_-")
    return MUSIC_ROOT / (safe or "unknown")


def ext_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def is_allowed(filename: str) -> bool:
    return ext_of(filename) in ALLOWED_EXT


def save_bytes(token: str, filename: str, data: bytes) -> tuple[str, int]:
    """把上传的字节写进这次会话的目录，返回 (落盘文件名, 字节数)"""
    folder = session_dir(token)
    folder.mkdir(parents=True, exist_ok=True)
    ext = ext_of(filename)
    stored = f"{uuid.uuid4().hex}{ext}"
    (folder / stored).write_bytes(data)
    return stored, len(data)


def file_path(token: str, filename: str) -> Path:
    return session_dir(token) / filename


def purge_session(conn: sqlite3.Connection, token: str) -> None:
    """退出登录：删这个会话的所有音乐行 + 删目录（不 commit，交给调用方）"""
    conn.execute("DELETE FROM music_tracks WHERE session_token = ?", (token,))
    shutil.rmtree(session_dir(token), ignore_errors=True)


def cleanup_orphans(conn: sqlite3.Connection) -> None:
    """启动时清一遍：会话已经不在了的音乐，行和文件都删掉"""
    live = {row["token"] for row in conn.execute("SELECT token FROM sessions")}

    conn.execute(
        """DELETE FROM music_tracks
            WHERE session_token NOT IN (SELECT token FROM sessions)"""
    )

    if not MUSIC_ROOT.is_dir():
        return
    live_dirs = {"".join(ch for ch in t if ch.isalnum() or ch in "_-") for t in live}
    for child in MUSIC_ROOT.iterdir():
        if child.is_dir() and child.name not in live_dirs:
            shutil.rmtree(child, ignore_errors=True)
