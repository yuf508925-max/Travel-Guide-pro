# -*- coding: utf-8 -*-
"""
api_guard.py —— 语音进程的"陪护"

由 voice_service.py 启动，环境变量 VOICE_PARENT_PID 传进来。
它负责：
  1. 真正启动 api_v2.py
  2. 用 WaitForSingleObject 盯住父进程句柄
     —— 父进程不管是正常退出、崩溃还是被强杀，句柄都会变成"已通知"，
        这时立刻结束 api_v2，避免留下占着显存的孤儿进程
"""

import ctypes
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(BASE, ".venv-gsv", "Scripts", "python.exe")
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0


def kill_tree(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def main() -> int:
    parent_pid = int(os.environ.get("VOICE_PARENT_PID", "0") or 0)
    env = os.environ.copy()
    env["PATH"] = os.path.join(BASE, "ffmpeg-bin") + os.pathsep + env.get("PATH", "")

    child = subprocess.Popen(
        [PYTHON, "api_v2.py", "-a", "127.0.0.1", "-p", os.environ.get("VOICE_PORT", "9880"),
         "-c", "furina_infer.yaml"],
        cwd=BASE,
        env=env,
    )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    parent_handle = None
    if parent_pid:
        parent_handle = kernel32.OpenProcess(SYNCHRONIZE, False, parent_pid)

    try:
        while True:
            if child.poll() is not None:
                return child.returncode or 0
            if parent_handle:
                result = kernel32.WaitForSingleObject(parent_handle, 1000)
                if result == WAIT_OBJECT_0:
                    print("[guard] 父进程已退出，关闭语音服务", flush=True)
                    kill_tree(child.pid)
                    return 0
            else:
                child.wait(timeout=1)
    except KeyboardInterrupt:
        kill_tree(child.pid)
        return 0


if __name__ == "__main__":
    sys.exit(main())