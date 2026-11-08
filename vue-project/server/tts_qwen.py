# =====================================================================
# tts_qwen.py —— Qwen-TTS 语音合成（阿里云百炼 DashScope）
# ---------------------------------------------------------------------
# 接口：POST https://dashscope.aliyuncs.com/api/v1/services/aigc/
#        multimodal-generation/generation
#   body: {"model": "qwen3-tts-flash",
#          "input": {"text": "...", "voice": "Cherry", "language_type": "Chinese"}}
#   返回：output.audio.url（wav，24 小时有效）
#
# 这里把音频下载成 bytes 再由后端返回给前端，好处：
#   · Key 不暴露给浏览器
#   · 不用处理 OSS 的跨域/防盗链
# =====================================================================

import asyncio
import json
import urllib.error
import urllib.request

try:
    # 走系统证书库，避免 CERTIFICATE_VERIFY_FAILED
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
UA = "TravelGuidePro/1.0"
TIMEOUT = 60.0
MAX_CHARS = 600          # 接口上限

# 音色暂时固定（界面上不再给选项，等接本地 GPT-SoVITS 后由模型决定）
DEFAULT_VOICE = "Cherry"

# 只有这几个是语音合成模型。填错成 qwen-audio-*-asr（语音识别）会报
# "url error, please check url!"，因为识别模型要的是音频地址而不是文字。
TTS_MODELS = ["qwen3-tts-flash", "qwen-tts"]
DEFAULT_MODEL = "qwen3-tts-flash"


class TtsError(Exception):
    """语音合成失败（Key 不对 / 文本为空 / 上游报错）"""


def _post_json(url: str, payload: dict, api_key: str) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": UA,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(detail).get("message") or detail
        except Exception:
            message = detail
        raise TtsError(f"语音合成失败（HTTP {exc.code}）：{message[:160]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TtsError(f"连不上语音服务：{exc}") from exc


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TtsError(f"音频下载失败：{exc}") from exc


def synthesize_sync(text: str, api_key: str, model: str, voice: str) -> bytes:
    clean = (text or "").strip()
    if not clean:
        raise TtsError("要朗读的文本是空的")
    if len(clean) > MAX_CHARS:
        clean = clean[:MAX_CHARS]

    # 防呆：模型名不是合成模型时，直接给出能看懂的提示
    if model and model not in TTS_MODELS:
        raise TtsError(
            f"模型「{model}」不是语音合成模型，请改成 {TTS_MODELS[0]}（设置 → 语音 → 模型）"
        )

    payload = {
        "model": model or DEFAULT_MODEL,
        "input": {
            "text": clean,
            "voice": voice or DEFAULT_VOICE,
            "language_type": "Chinese",
        },
    }
    data = _post_json(API_URL, payload, api_key)

    if data.get("code"):
        raise TtsError(f"语音合成失败：{data.get('message') or data['code']}")

    audio = ((data.get("output") or {}).get("audio")) or {}
    audio_url = audio.get("url")
    if not audio_url:
        raise TtsError("语音合成没有返回音频地址")
    return _download(audio_url)


async def synthesize(text: str, api_key: str, model: str, voice: str) -> bytes:
    return await asyncio.to_thread(synthesize_sync, text, api_key, model, voice)