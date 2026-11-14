# =====================================================================
# llm_trace.py —— 记录「后端 ↔ 大模型」的每一次对话
# ---------------------------------------------------------------------
# 每次调用模型（聊天 / 摘要 / 挑表情）都往这里写一条 JSON：
#   请求：model、base_url、messages（system/user/assistant 原文）
#   响应：最终拼好的文本（流式是边收边拼）或错误信息、耗时
#
# 两个出口：
#   1. 追加进 server/logs/llm_trace.jsonl（默认 8MB 自动轮转一次），
#      新开的监控端口（llm_monitor.py）直接读这个文件，不用登录、不碰主服务；
#   2. 内存里留最近 200 条，方便以后在主服务上挂个调试接口。
#
# 关掉：环境变量 LLM_TRACE=0（生产环境不想写盘时用）
# =====================================================================

import json
import os
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent / "logs"
_LOG_FILE = _LOG_DIR / "llm_trace.jsonl"

_MAX_BYTES = 8 * 1024 * 1024  # 单个日志文件上限，超了就换 .1
_enabled = os.environ.get("LLM_TRACE", "1") != "0"

_recent: deque[dict] = deque(maxlen=200)
_lock = threading.Lock()
_seq = 0


def _short(text: str, limit: int = 8000) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + f"…（共 {len(text)} 字）"


def record(
    kind: str,
    model: str,
    messages: list[dict],
    response: str = "",
    error: str = "",
    ms: int = 0,
    base_url: str = "",
    extra: dict | None = None,
) -> None:
    """写一条调用记录。任何异常都不能影响主流程，所以整段都包在 try 里。"""
    global _seq
    if not _enabled:
        return
    try:
        clean_messages = [
            {
                "role": str(m.get("role") or ""),
                "content": _short(str(m.get("content") or "")),
            }
            for m in (messages or [])
        ]
        item = {
            "id": 0,
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "kind": kind,
            "model": model,
            "base_url": base_url,
            "ms": int(ms),
            "messages": clean_messages,
            "response": _short(response),
            "error": error or "",
        }
        if extra:
            item.update(extra)

        with _lock:
            _seq += 1
            item["id"] = _seq
            _recent.append(item)
            _write(item)
    except Exception:
        # 监控/日志出问题绝不能把聊天搞崩
        pass


def _write(item: dict) -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if _LOG_FILE.exists() and _LOG_FILE.stat().st_size > _MAX_BYTES:
            backup = _LOG_FILE.with_suffix(".jsonl.1")
            backup.unlink(missing_ok=True)
            _LOG_FILE.rename(backup)
    except OSError:
        pass
    with _LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def snapshot(limit: int = 50) -> list[dict]:
    """最近几条（内存里那份），给调试接口用"""
    with _lock:
        items = list(_recent)[-limit:]
    return items


class Timer:
    """with Timer() as t: ... → t.ms 是耗时毫秒"""

    def __init__(self) -> None:
        self._start = 0.0
        self.ms = 0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self.ms = int((time.perf_counter() - self._start) * 1000)
