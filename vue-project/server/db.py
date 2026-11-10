# =====================================================================
# db.py —— SQLite 连接 + 建表
#   数据库文件：server/app.db（已在 .gitignore 里忽略）
#   六张表：
#     users          用户（用户名 + 密码哈希）
#     sessions       登录会话（随机 token → 用户），Session Cookie 里只放 token
#     user_providers 一个账号可以有多套 Key（提供商），各自带多个可选模型，
#                    其中 is_active=1 的那套是聊天当前使用的
#     route_searches 行程面板的搜索记录（城市 / 出发地 / 目的地 / 方式），
#                    每个账号只保留最近 20 条，面板打开时回填最近一条
#     user_map_settings 高德地图 Key / 安全密钥，一个账号一行
#     user_tts_settings 语音合成（Qwen-TTS）的 Key / 模型 / 音色，一个账号一行
# =====================================================================

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import keyvault

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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_providers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name       TEXT NOT NULL DEFAULT 'DeepSeek',
                api_key    TEXT NOT NULL DEFAULT '',
                base_url   TEXT NOT NULL DEFAULT '',
                models     TEXT NOT NULL DEFAULT '',
                model      TEXT NOT NULL DEFAULT '',
                is_active  INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_providers_user ON user_providers(user_id)"
        )


        # ---- 迁移：如果 user_providers 上还挂着 amap_* 列（上一版），搬过来再删列 ----
        provider_columns = {row["name"] for row in conn.execute("PRAGMA table_info(user_providers)")}
        if "amap_key" in provider_columns or "amap_security_code" in provider_columns:
            conn.execute(
                """
                INSERT INTO user_map_settings (user_id, amap_key, security_code)
                SELECT user_id, MAX(amap_key), MAX(amap_security_code)
                  FROM user_providers
                 GROUP BY user_id
                HAVING MAX(amap_key) <> '' OR MAX(amap_security_code) <> ''
                ON CONFLICT(user_id) DO UPDATE SET
                    amap_key      = excluded.amap_key,
                    security_code = excluded.security_code,
                    updated_at    = datetime('now')
                """
            )
            for column in ("amap_key", "amap_security_code"):
                if column in provider_columns:
                    try:
                        conn.execute(f"ALTER TABLE user_providers DROP COLUMN {column}")
                    except sqlite3.OperationalError:
                        # 老版本 SQLite 不支持 DROP COLUMN，留着也无害
                        pass

        # 行程搜索记录：按 user_id 隔离，一个账号只看得到自己的
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS route_searches (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                city        TEXT NOT NULL DEFAULT '',
                origin      TEXT NOT NULL DEFAULT '',
                destination TEXT NOT NULL DEFAULT '',
                mode        TEXT NOT NULL DEFAULT 'driving',
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_route_searches_user ON route_searches(user_id, id DESC)"
        )

        # 语音合成（和芙芙打电话）：Qwen-TTS 的 Key / 模型 / 音色
        #   prompt_text：本地 GPT-SoVITS 参考音频对应的文字，直接影响音色像不像
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_tts_settings (
                user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                api_key     TEXT NOT NULL DEFAULT '',
                model       TEXT NOT NULL DEFAULT 'qwen3-tts-flash',
                voice       TEXT NOT NULL DEFAULT 'Cherry',
                prompt_text TEXT NOT NULL DEFAULT '',
                updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        tts_columns = {row["name"] for row in conn.execute("PRAGMA table_info(user_tts_settings)")}
        if "prompt_text" not in tts_columns:
            conn.execute(
                "ALTER TABLE user_tts_settings ADD COLUMN prompt_text TEXT NOT NULL DEFAULT ''"
            )

        conn.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")

        # ---- Key 落盘加密：把历史明文逐条转成密文（幂等，已加密的跳过） ----
        #   库被拷走时只有密文；主密钥在 .keys/master.key（不进 Git）
        keyvault.migrate_plaintext(conn)
