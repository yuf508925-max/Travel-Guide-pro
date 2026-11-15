# -*- coding: utf-8 -*-
"""check_assets.py —— 检查语音服务需要的资源文件是否齐全

用法（在哪个目录执行都行）：
    python voice-service\\check_assets.py

全部齐全时退出码 0；缺文件时退出码 1，并打印缺什么、该放哪里。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # vue-project
VOICE = ROOT / "voice-service"
GSV = VOICE / "GPT_SoVITS"
MODELS = ROOT / "models" / "Furina_GPT_SoVITS"

MB = 1024 * 1024

# (相对路径, 最小体积, 说明)
GROUPS: list[tuple[str, str, list[tuple[Path, int, str]]]] = [
    (
        "语音 Python 环境",
        "按 README 第四节 3 创建：python -m venv voice-service\\.venv-gsv",
        [
            (VOICE / ".venv-gsv" / "Scripts" / "python.exe", 100_000, "voice-service/.venv-gsv/Scripts/python.exe"),
        ],
    ),
    (
        "GPT-SoVITS 底模（约 0.95 GB）",
        "见 README 第四节 4：python voice-service\\fetch_assets.py 或 huggingface-cli 下载",
        [
            (GSV / "pretrained_models" / "chinese-hubert-base" / "config.json", 1_000, "chinese-hubert-base/config.json"),
            (GSV / "pretrained_models" / "chinese-hubert-base" / "preprocessor_config.json", 100, "chinese-hubert-base/preprocessor_config.json"),
            (GSV / "pretrained_models" / "chinese-hubert-base" / "pytorch_model.bin", 150 * MB, "chinese-hubert-base/pytorch_model.bin"),
            (GSV / "pretrained_models" / "chinese-roberta-wwm-ext-large" / "config.json", 500, "chinese-roberta-wwm-ext-large/config.json"),
            (GSV / "pretrained_models" / "chinese-roberta-wwm-ext-large" / "tokenizer.json", 100_000, "chinese-roberta-wwm-ext-large/tokenizer.json"),
            (GSV / "pretrained_models" / "chinese-roberta-wwm-ext-large" / "pytorch_model.bin", 600 * MB, "chinese-roberta-wwm-ext-large/pytorch_model.bin"),
            (GSV / "pretrained_models" / "sv" / "pretrained_eres2netv2w24s4ep4.ckpt", 95 * MB, "sv/pretrained_eres2netv2w24s4ep4.ckpt"),
        ],
    ),
    (
        "G2PW 多音字模型（约 0.6 GB）",
        "见 README 第四节 4：python voice-service\\fetch_assets.py；缺它时首次合成会自动从 ModelScope 下载",
        [
            (GSV / "text" / "G2PWModel" / "g2pW.onnx", 550 * MB, "GPT_SoVITS/text/G2PWModel/g2pW.onnx"),
            (GSV / "text" / "G2PWModel" / "config.py", 100, "GPT_SoVITS/text/G2PWModel/config.py"),
        ],
    ),
    (
        "语种切分模型（约 0.13 GB）",
        "见 README 第四节 4：python voice-service\\fetch_assets.py；缺它时 /tts 会直接返回 400（Cache directory not found）",
        [
            (GSV / "pretrained_models" / "fast_langdetect" / "lid.176.bin", 120 * MB, "GPT_SoVITS/pretrained_models/fast_langdetect/lid.176.bin"),
        ],
    ),
    (
        "ffmpeg（约 0.2 GB）",
        "见 README 第四节 4：python voice-service\\fetch_assets.py，或手动解压 ffmpeg 的 bin\\*.exe（共享构建要把同目录 dll 一起放进来）",
        [
            (VOICE / "ffmpeg-bin" / "ffmpeg.exe", 100_000, "voice-service/ffmpeg-bin/ffmpeg.exe", "exe"),
            (VOICE / "ffmpeg-bin" / "ffprobe.exe", 100_000, "voice-service/ffmpeg-bin/ffprobe.exe", "exe"),
        ],
    ),
    (
        "芙宁娜音色权重（约 0.3 GB，仓库里没有）",
        "先跑 python voice-service\\fetch_assets.py 自动下载（ModelScope: leletxh/Furina_GPT_SoVITS）；ref.wav 通常随仓库提供",
        [
            (MODELS / "Funina-e15.ckpt", 140 * MB, "models/Furina_GPT_SoVITS/Funina-e15.ckpt（GPT 模型）"),
            (MODELS / "Funina_e8_s464.pth", 150 * MB, "models/Furina_GPT_SoVITS/Funina_e8_s464.pth（SoVITS 模型）"),
            (MODELS / "ref.wav", 100_000, "models/Furina_GPT_SoVITS/ref.wav（3~10 秒参考音频）"),
        ],
    ),
]


def human(size: int) -> str:
    if size >= MB:
        return f"{size / MB:.1f} MB"
    return f"{size / 1024:.0f} KB"


def check_file(path: Path, min_size: int) -> tuple[str, str]:
    """返回 (状态, 说明)：ok / missing / broken"""
    if not path.exists():
        return "missing", "缺失"
    size = path.stat().st_size
    if size < min_size:
        return "broken", f"只有 {human(size)}，下载不完整（可能是 HTML 错误页或 LFS 指针）"
    return "ok", human(size)


def check_exe(path: Path, min_size: int) -> tuple[str, str]:
    """可执行文件：先看体积，再真的跑一下 -version，避免「能看见文件但跑不起来」。"""
    state, note = check_file(path, min_size)
    if state != "ok":
        return state, note
    try:
        proc = subprocess.run([str(path), "-version"], capture_output=True, timeout=30)
    except Exception as exc:  # noqa: BLE001 - 起不来就是坏文件或缺 dll
        return "broken", f"无法运行（{type(exc).__name__}）"
    out = (proc.stdout or b"").decode("utf-8", "replace")
    if proc.returncode != 0 or "version" not in out.lower():
        first = out.strip().splitlines()[0][:40] if out.strip() else "无输出"
        return "broken", f"运行失败（缺同目录 dll？）：{first}"
    version = out.splitlines()[0].split()[2] if len(out.splitlines()[0].split()) > 2 else "ok"
    return "ok", f"{note}，可运行（{version}）"


def main() -> int:
    print("=" * 62)
    print("  语音服务资源检查")
    print(f"  项目目录: {ROOT}")
    print("=" * 62)

    total = 0
    missing = 0
    for title, hint, files in GROUPS:
        rows = []
        for item in files:
            path, min_size, label = item[0], item[1], item[2]
            kind = item[3] if len(item) > 3 else "file"
            state, note = check_exe(path, min_size) if kind == "exe" else check_file(path, min_size)
            rows.append((path, min_size, label, state, note))
        bad = [row for row in rows if row[3] != "ok"]
        total += len(rows)
        missing += len(bad)
        flag = "OK " if not bad else "!! "
        print(f"\n[{flag}] {title}")
        for _, _, label, state, note in rows:
            mark = "  ok  " if state == "ok" else "  缺  "
            print(f"   {mark} {label:<58} {note}")
        if bad:
            print(f"        -> 修复：{hint}")

    print("\n" + "-" * 62)
    if missing == 0:
        print(f"全部 {total} 个文件都在，可以启动语音服务了：")
        print("   powershell -NoProfile -ExecutionPolicy Bypass -File voice-service\\start_furina_api.ps1")
        return 0
    print(f"还缺 {missing} / {total} 个文件。按上面每组的「修复」提示补齐后重新运行本脚本。")
    print("一键补装：python voice-service\\fetch_assets.py")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
