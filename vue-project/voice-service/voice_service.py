# -*- coding: utf-8 -*-
"""
voice_service.py —— 芙宁娜本地语音服务的"管家"

作用：
  1. 启动 api_guard.py（它再去启动 GPT-SoVITS 的 api_v2.py）
  2. 窗口关闭 / 进程被杀 / 崩溃时，guard 发现父进程没了会自动结束 api_v2
  3. 看门狗：后端（默认 8000）从"在线"变成"连续 3 次连不上"（约 15 秒），
     自动关掉语音服务，避免占着显存

用法：
  .venv-gsv\Scripts\python.exe voice_service.py
可选环境变量：
  APP_HEALTH_URL   后端健康检查地址，默认 http://127.0.0.1:8000/api/health
  VOICE_PORT       语音服务端口，默认 9880
"""

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(BASE, ".venv-gsv", "Scripts", "python.exe")
APP_HEALTH_URL = os.environ.get("APP_HEALTH_URL", "http://127.0.0.1:8000/api/health")
VOICE_PORT = int(os.environ.get("VOICE_PORT", "9880"))
CHECK_INTERVAL = 5.0
MISS_LIMIT = 3


def kill_tree(pid: int) -> None:
    """连同子孙进程一起结束：api_v2 是 guard 的子进程，只 terminate 会留下孤儿"""
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def health_ok() -> bool:
    try:
        request = urllib.request.Request(APP_HEALTH_URL, headers={"User-Agent": "voice-service"})
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def main() -> int:
    env = os.environ.copy()
    env["PATH"] = os.path.join(BASE, "ffmpeg-bin") + os.pathsep + env.get("PATH", "")
    env["VOICE_PARENT_PID"] = str(os.getpid())
    env["VOICE_PORT"] = str(VOICE_PORT)

    print("=== 芙宁娜本地语音服务 ===", flush=True)
    print(f"    语音端口: {VOICE_PORT}", flush=True)
    print(f"    监听后端: {APP_HEALTH_URL}", flush=True)
    print("    关掉这个窗口 / 后端退出，语音服务都会自动关闭", flush=True)

    child = subprocess.Popen([PYTHON, "api_guard.py"], cwd=BASE, env=env)

    stop = threading.Event()

    def watchdog():
        seen_app = False
        misses = 0
        while child.poll() is None and not stop.is_set():
            time.sleep(CHECK_INTERVAL)
            if stop.is_set() or child.poll() is not None:
                break
            ok = health_ok()
            if ok:
                if not seen_app:
                    print("    [守护] 已连上后端，开始监控", flush=True)
                seen_app = True
                misses = 0
                continue
            if not seen_app:
                print(f"    [守护] 等后端上线中… ({APP_HEALTH_URL})", flush=True)
                continue
            misses += 1
            print(f"    [守护] 后端没响应 {misses}/{MISS_LIMIT}", flush=True)
            if misses >= MISS_LIMIT:
                print("    [守护] 后端已退出，自动关闭语音服务", flush=True)
                stop.set()
                kill_tree(child.pid)
                return

    threading.Thread(target=watchdog, daemon=True).start()

    try:
        return child.wait()
    except KeyboardInterrupt:
        print("\n    收到中断，正在关闭语音服务…", flush=True)
        kill_tree(child.pid)
        return 0


if __name__ == "__main__":
    sys.exit(main())
