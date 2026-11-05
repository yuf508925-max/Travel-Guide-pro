# =====================================================================
# db.py —— SQLite 连接 + 建表
#   数据库文件：server/app.db（已在 .gitignore 里忽略）
#   两张表：
#     users    用户（用户名 + 密码哈希）
#     sessions 登录会话（随机 token → 用户），Session Cookie 里只放 token
# =====================================================================

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_PATH = Path(__file__).parent / "app.db"


def get_db() -> sqlite3.Connection:
    """每次拿一个新连接（sqlite 单文件，开销很小）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row          # 查询结果可按列名取值：row["username"]
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    """with db() as conn: ... —— 自动提交 / 回滚 / 关闭连接"""
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """启动时建表（已存在就跳过），顺手清掉过期会话"""
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token      TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at TEXT NOT NULL
            )
            """
        )
        conn.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
