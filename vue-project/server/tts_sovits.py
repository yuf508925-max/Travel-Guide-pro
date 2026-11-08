# =====================================================================
# tts_sovits.py —— 本地 GPT-SoVITS 语音服务（api_v2.py）
# ---------------------------------------------------------------------
# 模型：models/Furina_GPT_SoVITS/
#   Funina_e8_s464.pth   SoVITS 声学模型
#   Funina-e15.ckpt      GPT 模型
#
# 用法：先在本地把 GPT-SoVITS 的 api_v2.py 跑起来（默认 9880 端口），
# 这里用 POST /tts 让它合成，返回 wav 字节。
#
# 注意：GPT-SoVITS 推理必须带一段"参考音频 + 对应文本"（ref_audio_path /
# prompt_text），微调模型也一样。参考音频默认找 models/Furina_GPT_SoVITS/ref.wav。
# =====================================================================

import asyncio
import json
import urllib.error
import urllib.request
from pathlib import Path

from .config import (
    SOVITS_API_URL,
    SOVITS_USE_PROMPT_TEXT,
    SOVITS_PROMPT_LANG,
    SOVITS_PROMPT_TEXT,
    SOVITS_REF_AUDIO,
    SOVITS_TEXT_LANG,
)

TIMEOUT = 180.0


class SovitsError(Exception):
    """本地语音服务不可用 / 合成失败"""


def ref_audio_path() -> Path:
    return Path(SOVITS_REF_AUDIO)


def local_ready() -> bool:
    return ref_audio_path().is_file()


def synthesize_sync(text: str, prompt_text: str = "") -> bytes:
    clean = (text or "").strip()
    if not clean:
        raise SovitsError("要朗读的文本是空的")

    ref = ref_audio_path()
    if not ref.is_file():
        raise SovitsError(f"缺少参考音频：{ref}（放一段 3~10 秒的干净人声，命名 ref.wav）")

    payload = {
        "text": clean,
        "text_lang": SOVITS_TEXT_LANG,
        "ref_audio_path": str(ref),
        "prompt_lang": SOVITS_PROMPT_LANG,
        # 只有确认参考音频与文字匹配时才发送，否则模型会把提示也念出来
        "prompt_text": (prompt_text or SOVITS_PROMPT_TEXT) if SOVITS_USE_PROMPT_TEXT else "",
        "text_split_method": "cut5",
        "batch_size": 1,
        "media_type": "wav",
        "streaming_mode": False,
        # —— 更像人一点的采样参数 ——
        # temperature 低一点更稳，top_k/top_p 适中保留语气起伏
        "temperature": 0.66,
        "top_k": 15,
        "top_p": 0.85,
        "speed_factor": 1.0,
        "fragment_interval": 0.25,
        "parallel_infer": True,
    }

    request = urllib.request.Request(
        SOVITS_API_URL.rstrip("/") + "/tts",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            audio = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise SovitsError(f"本地语音服务返回 HTTP {exc.code}：{detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SovitsError(
            f"连不上本地语音服务 {SOVITS_API_URL}（先启动 GPT-SoVITS 的 api_v2.py）"
        ) from exc

    if len(audio) < 1000:
        raise SovitsError("本地语音服务返回的音频是空的")
    return audio


async def synthesize(text: str, prompt_text: str = "") -> bytes:
    return await asyncio.to_thread(synthesize_sync, text, prompt_text)