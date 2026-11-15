# -*- coding: utf-8 -*-
"""fetch_assets.py —— 一键补装语音服务需要的公开资源（不含芙宁娜音色权重）

会用到的下载源（国内可直连）：
  * GPT-SoVITS 底模   https://hf-mirror.com/lj1995/GPT-SoVITS
  * G2PW 多音字模型    https://www.modelscope.cn/models/kamiorinn/g2pw
  * ffmpeg            https://www.gyan.dev/ffmpeg/builds/

用法（在项目根目录 vue-project 或任意目录执行都行）：
    python voice-service\\fetch_assets.py                 # 下载全部公开资源（约 1.75 GB）
    python voice-service\\fetch_assets.py --with-v2-base   # 额外下载 v2 官方底模（约 0.35 GB，可跳过）
    python voice-service\\fetch_assets.py --skip-ffmpeg --skip-g2pw
    python voice-service\\fetch_assets.py --dry-run        # 只打印将下载的文件

已存在的文件会跳过；下载中断后会从 .part 文件续传。
芙宁娜音色权重（Funina-e15.ckpt / Funina_e8_s464.pth）没有公开地址，脚本最后会提示手动放置。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICE = ROOT / "voice-service"
GSV = VOICE / "GPT_SoVITS"
PRETRAINED = GSV / "pretrained_models"
FFMPEG_DIR = VOICE / "ffmpeg-bin"
G2PW_DIR = GSV / "text" / "G2PWModel"

MB = 1024 * 1024
CHUNK = 1024 * 1024

HF_DEFAULT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
HF_REPO = "lj1995/GPT-SoVITS"

# (仓库内路径, 期望字节数)
HF_FILES = [
    ("chinese-hubert-base/config.json", 1_449),
    ("chinese-hubert-base/preprocessor_config.json", 212),
    ("chinese-hubert-base/pytorch_model.bin", 188_811_417),
    ("chinese-roberta-wwm-ext-large/config.json", 963),
    ("chinese-roberta-wwm-ext-large/tokenizer.json", 268_962),
    ("chinese-roberta-wwm-ext-large/pytorch_model.bin", 651_225_145),
    ("sv/pretrained_eres2netv2w24s4ep4.ckpt", 107_528_697),
]
HF_V2_FILES = [
    ("gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt", 155_315_150),
    ("gsv-v2final-pretrained/s2D2333k.pth", 93_534_164),
    ("gsv-v2final-pretrained/s2G2333k.pth", 106_035_259),
]

G2PW_URL = "https://www.modelscope.cn/models/kamiorinn/g2pw/resolve/master/G2PWModel_1.1.zip"
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

# 芙宁娜音色权重（作者自训，已传到 ModelScope）
FURINA_DIR = ROOT / "models" / "Furina_GPT_SoVITS"
MS_FURINA_REPO = "https://www.modelscope.cn/models/leletxh/Furina_GPT_SoVITS/resolve/master"
FURINA_FILES = [
    ("Funina-e15.ckpt", 155_313_312),
    ("Funina_e8_s464.pth", 172_765_299),
]

HEADERS = {"User-Agent": "travel-guide-fetch-assets/1.0"}


def human(size: float) -> str:
    return f"{size / MB:.1f} MB"


def rel(path: Path) -> str:
    """返回相对项目根目录的路径；不在项目内时退回绝对路径。"""
    try:
        return str(path.resolve().relative_to(ROOT))
    except (ValueError, OSError):
        return str(path)


def download(url: str, dest: Path, expected: int | None = None) -> None:
    """支持断点续传的下载；先写 dest.part，完整后再改名。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")

    if dest.exists() and (expected is None or dest.stat().st_size == expected):
        print(f"   跳过（已存在）: {rel(dest)}")
        return
    if dest.exists() and expected is not None and dest.stat().st_size != expected:
        print(f"   已存在的文件大小不对，重新下载: {rel(dest)}")
        dest.unlink()

    existing = part.stat().st_size if part.exists() else 0
    if expected and existing > expected:
        part.unlink()
        existing = 0

    last_error: Exception | None = None
    for attempt in range(1, 4):
        headers = dict(HEADERS)
        if existing:
            headers["Range"] = f"bytes={existing}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                mode = "ab" if existing and response.status == 206 else "wb"
                if mode == "wb":
                    existing = 0
                total = int(response.headers.get("Content-Length") or 0) + existing
                done = existing
                started = time.time()
                last_report = 0.0
                with open(part, mode) as fh:
                    while True:
                        chunk = response.read(CHUNK)
                        if not chunk:
                            break
                        fh.write(chunk)
                        done += len(chunk)
                        now = time.time()
                        if now - last_report > 2:
                            last_report = now
                            speed = (done - existing) / max(now - started, 0.001) / MB
                            pct = f" {done * 100 // total:3d}%" if total else ""
                            print(f"\r   {dest.name}  {human(done)} / {human(total) if total else '?'}{pct}  {speed:.1f} MB/s", end="")
                print()

            if expected is not None and part.stat().st_size != expected:
                raise IOError(f"大小不对：期望 {expected} 字节，实际 {part.stat().st_size} 字节")
            if part.exists() and part.stat().st_size == 0:
                raise IOError("下载到的文件是空的")
            part.replace(dest)
            print(f"   完成: {rel(dest)}")
            return
        except Exception as exc:  # noqa: BLE001 - 网络异常统一重试
            last_error = exc
            print(f"\n   第 {attempt} 次下载失败: {exc}")
            if part.exists():
                existing = part.stat().st_size
            time.sleep(2 * attempt)

    raise SystemExit(f"下载失败（已重试 3 次）：{url}\n原因：{last_error}")


def fetch_hf(endpoint: str, files: list[tuple[str, int]]) -> None:
    print(f"\n[1/4] GPT-SoVITS 底模 -> {PRETRAINED}  (源: {endpoint})")
    for rel, size in files:
        url = f"{endpoint.rstrip('/')}/{HF_REPO}/resolve/main/{rel}?download=true"
        download(url, PRETRAINED / rel, size)


def fetch_g2pw() -> None:
    print(f"\n[2/4] G2PW 多音字模型 -> {G2PW_DIR}  (源: ModelScope)")
    if (G2PW_DIR / "g2pW.onnx").exists():
        print("   跳过（已存在）")
        return

    zip_path = VOICE / "G2PWModel_1.1.zip"
    download(G2PW_URL, zip_path)

    tmp = GSV / "text" / "_g2pw_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    print("   解压中…")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmp)

    hits = list(tmp.rglob("g2pW.onnx"))
    if not hits:
        shutil.rmtree(tmp, ignore_errors=True)
        raise SystemExit("解压后没找到 g2pW.onnx，压缩包可能不完整；删掉 voice-service/G2PWModel_1.1.zip 后重试。")

    src = hits[0].parent
    shutil.rmtree(G2PW_DIR, ignore_errors=True)
    shutil.move(str(src), str(G2PW_DIR))
    shutil.rmtree(tmp, ignore_errors=True)
    zip_path.unlink(missing_ok=True)
    print(f"   完成: {rel(G2PW_DIR)}")


def fetch_ffmpeg() -> None:
    print(f"\n[4/4] ffmpeg -> {FFMPEG_DIR}  (源: gyan.dev)")
    if (FFMPEG_DIR / "ffmpeg.exe").exists() and (FFMPEG_DIR / "ffprobe.exe").exists():
        print("   跳过（已存在）")
        return

    zip_path = VOICE / "_ffmpeg.zip"
    download(FFMPEG_URL, zip_path)

    print("   解压 ffmpeg.exe / ffprobe.exe…")
    wanted = {"ffmpeg.exe", "ffprobe.exe"}
    found: dict[str, zipfile.ZipInfo] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            base = name.rsplit("/", 1)[-1].lower()
            if base in wanted and "/bin/" in f"/{name.lower()}":
                found[base] = info
        if len(found) != 2:
            raise SystemExit("ffmpeg 压缩包结构不对，没找到 bin/ffmpeg.exe 和 bin/ffprobe.exe；删掉 voice-service/_ffmpeg.zip 后重试。")
        FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
        for base, info in found.items():
            with zf.open(info) as src, open(FFMPEG_DIR / base, "wb") as dst:
                shutil.copyfileobj(src, dst)

    zip_path.unlink(missing_ok=True)
    print(f"   完成: {rel(FFMPEG_DIR)}")


def fetch_furina() -> None:
    print(f"\n[3/4] 芙宁娜音色权重 -> {FURINA_DIR}  (源: ModelScope leletxh/Furina_GPT_SoVITS)")
    for name, size in FURINA_FILES:
        download(f"{MS_FURINA_REPO}/{name}", FURINA_DIR / name, size)


def report_reference_audio() -> None:
    ref = FURINA_DIR / "ref.wav"
    print("\n" + "-" * 62)
    if ref.exists():
        print("参考音频 ref.wav 也在，全部资源齐了。")
    else:
        print("还差参考音频（脚本不下，3~10 秒干净人声的 wav）：")
        print(f"  - {rel(ref)}")
        print("\n获取方式：")
        print("  1. 从原来那台能跑语音的电脑，拷一份 models/Furina_GPT_SoVITS/ref.wav；")
        print("  2. 自己截一段 3~10 秒芙宁娜的语音，存成 wav 放进去。")
    print("\n检查全部资源：python voice-service\\check_assets.py")


def main() -> int:
    parser = argparse.ArgumentParser(description="补装 GPT-SoVITS 语音服务需要的公开资源")
    parser.add_argument("--hf-endpoint", default=HF_DEFAULT, help=f"HuggingFace 镜像，默认 {HF_DEFAULT}")
    parser.add_argument("--with-v2-base", action="store_true", help="额外下载 v2 官方底模（只有切回官方 v2 音色时才需要）")
    parser.add_argument("--skip-g2pw", action="store_true", help="跳过 G2PW 多音字模型")
    parser.add_argument("--skip-ffmpeg", action="store_true", help="跳过 ffmpeg")
    parser.add_argument("--skip-furina", action="store_true", help="跳过芙宁娜音色权重")
    parser.add_argument("--dry-run", action="store_true", help="只打印要下载什么，不真的下载")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 62)
    print("  语音资源补装")
    print(f"  项目目录: {ROOT}")
    print(f"  下载源  : {args.hf_endpoint}")
    print("=" * 62)

    files = list(HF_FILES)
    if args.with_v2_base:
        files += HF_V2_FILES

    if args.dry_run:
        print("\n将下载：")
        for rel, size in files:
            print(f"  - pretrained_models/{rel}  ({human(size)})")
        if not args.skip_g2pw:
            print("  - GPT_SoVITS/text/G2PWModel/（从 ModelScope 下载 zip 后解压）")
        if not args.skip_furina:
            for name, size in FURINA_FILES:
                print(f"  - models/Furina_GPT_SoVITS/{name}  ({human(size)})  [ModelScope]")
        if not args.skip_ffmpeg:
            print("  - ffmpeg-bin/ffmpeg.exe、ffprobe.exe（从 gyan.dev 下载 zip 后解压）")
        print("\n（--dry-run：没有实际下载）")
        return 0

    fetch_hf(args.hf_endpoint, files)
    if args.skip_g2pw:
        print("\n[2/4] 已跳过 G2PW")
    else:
        fetch_g2pw()
    if args.skip_furina:
        print("\n[3/4] 已跳过芙宁娜音色权重")
    else:
        fetch_furina()
    if args.skip_ffmpeg:
        print("\n[4/4] 已跳过 ffmpeg")
    else:
        fetch_ffmpeg()

    report_reference_audio()
    return 0


if __name__ == "__main__":
    sys.exit(main())
