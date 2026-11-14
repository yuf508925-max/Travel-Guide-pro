# =====================================================================
# db.py —— SQLite 连接 + 建表
#   数据库文件：server/app.db（已在 .gitignore 里忽略）
#   六张表：
#     users          用户（用户名 + 密码哈希 + role：user/admin）
#     sessions       登录会话（随机 token → 用户），Session Cookie 里只放 token
#     user_providers 一个账号可以有多套 Key（提供商），各自带多个可选模型，
#                    其中 is_active=1 的那套是聊天当前使用的
#     route_searches 搜索记录（kind=route 行程：城市/出发地/目的地/方式；kind=vlog 看视频的关键词）,
#                    每个账号只保留最近 20 条，面板打开时回填最近一条
#     user_map_settings 高德地图 Key / 安全密钥，一个账号一行
#     user_tts_settings 语音合成（Qwen-TTS）的 Key / 模型 / 音色，一个账号一行
#     usage_events   调用打点（visit=页面访问 / amap=高德接口 / chat、tts、trains 等），
#                    只保留最近一年
#     feedback       用户在前台「设置 → 意见反馈」写给管理员的留言
#     announcements  公告（后台发布，前台顶栏「公告」里看）
#     music_tracks   用户上传的音乐（文件在 server/tmp_music/<会话 token>/，
#                    表里记文件名 / 大小 / 排列位置；退出登录或会话过期就一起删）
# =====================================================================

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import keyvault, music_store
from .config import ADMIN_PASSWORD, ADMIN_USERNAME
from .security import hash_password, verify_password

DB_PATH = Path(__file__).parent / "app.db"

# usage_events 只留最近一年：写的时候就把过期时间算好，清的时候照 sessions 的规矩来
USAGE_RETENTION = "+1 year"


def purge_old_usage(conn: sqlite3.Connection) -> int:
    """删掉过了期的打点，返回删了几行。

    和 sessions 完全一套逻辑：只看 expires_at，到期就真删。
    建表 / 迁移时给的过期时间是 created_at + 1 year，所以效果就是「留着最近一年」。
    idx_usage_expires 正好覆盖这个条件。
    """
    cur = conn.execute(
        "DELETE FROM usage_events"
        " WHERE expires_at IS NOT NULL AND expires_at <> ''"
        "   AND expires_at <= datetime('now')"
    )
    return cur.rowcount or 0


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


CONVERSATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS conversations (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title      TEXT    NOT NULL DEFAULT '新的对话',
  summary    TEXT    NOT NULL DEFAULT '',
  created_at TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, updated_at DESC);
"""

# 记忆条目：一条对话可以有很多条，删对话时跟着删（ON DELETE CASCADE）
MEMORIES_TABLE = """
CREATE TABLE IF NOT EXISTS memories (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  kind            TEXT    NOT NULL DEFAULT 'fact',
  content         TEXT    NOT NULL,
  created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mem_conv ON memories(conversation_id);
CREATE INDEX IF NOT EXISTS idx_mem_user ON memories(user_id);
"""


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
        # ---- 迁移：老库没有 role 列时补上（默认 user，管理员是 admin） ----
        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        if "role" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")

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


        # ---- 调用打点：访问量 / 高德地图调用 / 各家 API 调用量 ----
        # kind：visit（页面访问）| amap（高德）| chat | tts | trains | weather |
        #       routes | providers | map | auth | poster | trip | other
        # detail：更细的动作名，比如 amap 的 transfer / driving / place-search
        # user_id：必填 —— 认不出是谁的调用不写入（写入前在 usage.record 里就拦掉了）
        # expires_at：写的时候就算好「一年后」，到点由 purge_old_usage 真删（同 sessions）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                kind       TEXT NOT NULL,
                detail     TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at TEXT NOT NULL DEFAULT (datetime('now', '+1 year'))
            )
            """
        )
        # ---- 迁移：老库的 user_id 允许 NULL，重建表改成 NOT NULL ----
        #   1) 先清掉认不出用户的那些行（截图里 user_id 是 NULL 的都是登录前的请求）
        #   2) 建新表 + 拷数据 + 删旧表 + 改名（SQLite 不能直接改列约束）
        #   3) 索引必须重建（DROP TABLE 会把索引一起删掉）
        usage_info = {row["name"]: row for row in conn.execute("PRAGMA table_info(usage_events)")}
        if usage_info.get("user_id") is not None and not usage_info["user_id"]["notnull"]:
            conn.execute("DELETE FROM usage_events WHERE user_id IS NULL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_events_new (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    kind       TEXT NOT NULL,
                    detail     TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    expires_at TEXT NOT NULL DEFAULT (datetime('now', '+1 year'))
                )
                """
            )
            conn.execute(
                """
                INSERT INTO usage_events_new (id, user_id, kind, detail, created_at, expires_at)
                     SELECT e.id, e.user_id, e.kind, e.detail, e.created_at, e.expires_at
                       FROM usage_events e
                       JOIN users u ON u.id = e.user_id
                """
            )
            conn.execute("DROP TABLE usage_events")
            conn.execute("ALTER TABLE usage_events_new RENAME TO usage_events")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_time ON usage_events(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_events(user_id, kind)"
        )
        # ---- 迁移：老库没有 expires_at，补上并按 created_at + 1 年回填 ----
        usage_columns = {row["name"] for row in conn.execute("PRAGMA table_info(usage_events)")}
        if "expires_at" not in usage_columns:
            conn.execute("ALTER TABLE usage_events ADD COLUMN expires_at TEXT NOT NULL DEFAULT ''")
        conn.execute(
            """
            UPDATE usage_events
               SET expires_at = datetime(created_at, '+1 year')
             WHERE expires_at IS NULL OR expires_at = ''
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_expires ON usage_events(expires_at)"
        )

        # ---- 用户反馈：前台设置里发，后台消息窗口读 ----
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
                username   TEXT NOT NULL DEFAULT '',
                content    TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        # ---- 公告：管理员在后台发布，所有登录用户在前台的「公告」里看到 ----
        #   pinned=1 的排在前面；publisher 记发布人的用户名（人删了也不影响这条公告）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS announcements (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT NOT NULL,
                content    TEXT NOT NULL DEFAULT '',
                pinned     INTEGER NOT NULL DEFAULT 0,
                publisher  TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_notices_time ON announcements(pinned DESC, id DESC)"
        )

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
                -- 同一条记录空间放两类搜索：route=行程、vlog=看视频（关键词存 origin）
                kind        TEXT NOT NULL DEFAULT 'route',
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        # 老库补列：CREATE TABLE IF NOT EXISTS 不会给已有表加字段。
        # 必须放在建索引之前，否则索引里引用的 kind 还不存在。
        route_columns = {row["name"] for row in conn.execute("PRAGMA table_info(route_searches)")}
        if "kind" not in route_columns:
            conn.execute("ALTER TABLE route_searches ADD COLUMN kind TEXT NOT NULL DEFAULT 'route'")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_route_searches_user ON route_searches(user_id, kind, id DESC)"
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

        # ---- 模型库：管理员维护的「认识哪些模型」，带类型（语言 / 语音合成） ----
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS model_catalog (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL UNIQUE,
                vendor     TEXT NOT NULL DEFAULT '',
                kind       TEXT NOT NULL DEFAULT 'chat',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.executescript(CONVERSATIONS_TABLE)
        conn.executescript(MEMORIES_TABLE)
        # ---- 用户上传的音乐：文件在 server/tmp_music/<会话 token>/ 下 ----
        conn.executescript(music_store.MUSIC_TABLE)
        # ---- 迁移：对话记录「已经总结到第几条消息」 ----
        conv_columns = {row["name"] for row in conn.execute("PRAGMA table_info(conversations)")}
        if "summarized_upto" not in conv_columns:
            conn.execute(
                "ALTER TABLE conversations ADD COLUMN summarized_upto INTEGER NOT NULL DEFAULT 0"
            )
        # ---- 老数据迁移：把只有 summary 的对话转成一条记忆 ----
        conn.execute(
            """
            INSERT INTO memories (user_id, conversation_id, kind, content)
            SELECT c.user_id, c.id, 'summary', substr(c.summary, 1, 120)
              FROM conversations c
             WHERE c.summary <> ''
               AND NOT EXISTS (
                     SELECT 1 FROM memories m WHERE m.conversation_id = c.id
                   )
            """
        )
        _seed_models(conn)

        conn.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")

        # ---- 打点表只留一年（启动时清一次，运行期由 usage.record 每天兜一次）----
        try:
            purge_old_usage(conn)
        except Exception:
            pass          # 清理失败不该影响启动

        # ---- 会话没了（过期 / 被踢）→ 它上传的音乐也一起清掉 ----
        #   行删掉，server/tmp_music/<token>/ 目录也删掉
        try:
            music_store.cleanup_orphans(conn)
        except Exception:
            pass          # 临时目录清理失败不该影响启动

        # ---- Key 落盘加密：把历史明文逐条转成密文（幂等，已加密的跳过） ----
        #   库被拷走时只有密文；主密钥在 .keys/master.key（不进 Git）
        keyvault.migrate_plaintext(conn)

        # ---- 内置管理员：没有就建，有就校正角色/密码 ----
        _ensure_admin(conn)


DEFAULT_MODELS = [
    ("DeepSeek-V3.2", "DeepSeek", "chat"),
    ("DeepSeek-R1", "DeepSeek", "chat"),
    ("GPT-4o", "OpenAI", "chat"),
    ("Claude Sonnet 4.5", "Anthropic", "chat"),
    ("Qwen-Max", "阿里云百炼", "chat"),
    ("GLM-4.6", "智谱", "chat"),
    ("Kimi K2", "月之暗面", "chat"),
    ("qwen3-tts-flash", "阿里云百炼", "tts"),
    ("GPT-SoVITS · 芙宁娜", "本地", "tts"),
    ("CosyVoice 2", "阿里云百炼", "tts"),
]


def _seed_models(conn: sqlite3.Connection) -> None:
    """首次启动灌 10 个常见模型；已存在的名字不覆盖（管理员可能改过厂商/类型）。"""
    if conn.execute("SELECT COUNT(*) AS n FROM model_catalog").fetchone()["n"]:
        return
    conn.executemany(
        "INSERT OR IGNORE INTO model_catalog (name, vendor, kind) VALUES (?, ?, ?)",
        DEFAULT_MODELS,
    )


def _ensure_admin(conn: sqlite3.Connection) -> None:
    """保证库里有一个可用的管理员账号（默认 admin / 123456）。

    幂等：每次启动都会跑，但只有在缺失/不一致时才写库。
      1. 没有这个用户名 → 插入（role='admin'）
      2. 有但角色不是 admin → 提权
      3. 有但密码不是 ADMIN_PASSWORD → 重置（保证你拿到的账号密码一定能登进来）
    """
    row = conn.execute(
        "SELECT id, password_hash, role FROM users WHERE username = ?",
        (ADMIN_USERNAME,),
    ).fetchone()

    if row is None:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            (ADMIN_USERNAME, hash_password(ADMIN_PASSWORD)),
        )
        return

    if row["role"] != "admin":
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (row["id"],))

    if not verify_password(ADMIN_PASSWORD, row["password_hash"]):
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(ADMIN_PASSWORD), row["id"]),
        )
