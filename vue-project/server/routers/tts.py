# =====================================================================
# routers/tts.py —— 语音合成（和芙芙打电话用）
#   GET  /api/tts/settings  读当前账号的 TTS Key / 模型 / 音色
#   PUT  /api/tts/settings  保存（api_key 留空 = 不修改）
#   POST /api/tts/speak     合成一段话，直接返回 audio/wav
#
# Key 存在 user_tts_settings 表，和聊天 Key、地图 Key 一样按账号隔离。
# =====================================================================

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..db import db
from ..llm_settings import mask_key
from ..config import SOVITS_API_URL, SOVITS_PROMPT_TEXT
from ..tts_qwen import DEFAULT_MODEL, DEFAULT_VOICE, TTS_MODELS, TtsError, synthesize
from ..tts_sovits import SovitsError, local_ready, ref_audio_path
from ..tts_sovits import synthesize as synthesize_local
from .auth import current_user

router = APIRouter(prefix="/api/tts", tags=["tts"])


class TtsSettingsIn(BaseModel):
    api_key: str = Field(default="", max_length=200)
    model: str = Field(default=DEFAULT_MODEL, max_length=60)
    # 本地 GPT-SoVITS 参考音频对应的文字（直接影响音色像不像）
    prompt_text: str = Field(default="", max_length=600)


class SpeakIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=600)


def _settings_of(user_id: int) -> dict:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM user_tts_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
    if not row:
        return {"api_key": "", "model": DEFAULT_MODEL, "prompt_text": SOVITS_PROMPT_TEXT}

    model = (row["model"] or "").strip()
    # 老数据里可能存过 ASR 模型名，这里按默认合成模型处理
    if model not in TTS_MODELS:
        model = DEFAULT_MODEL
    return {
        "api_key": row["api_key"] or "",
        "model": model,
        # 库里没填就用 config 里写死的默认参考文本
        "prompt_text": (row["prompt_text"] or "").strip() or SOVITS_PROMPT_TEXT,
    }


@router.get("/settings")
def get_settings(user: dict = Depends(current_user)):
    settings = _settings_of(user["id"])
    key = settings["api_key"]
    return {
        "has_key": bool(key),
        "key_masked": mask_key(key) if key else "",
        "model": settings["model"],
        "prompt_text": settings.get("prompt_text", ""),
        "models": TTS_MODELS,
        "default_model": DEFAULT_MODEL,
        # 本地音色（GPT-SoVITS）的状态：前端拿来做提示
        "local": {
            "url": SOVITS_API_URL,
            "ref_audio": str(ref_audio_path()),
            "ready": local_ready(),
        },
    }


@router.put("/settings")
def put_settings(body: TtsSettingsIn, user: dict = Depends(current_user)):
    model = body.model.strip() or DEFAULT_MODEL
    if model not in TTS_MODELS:
        raise HTTPException(
            400,
            f"「{model}」不是语音合成模型，请选择 {TTS_MODELS[0]}",
        )
    new_key = body.api_key.strip()
    # 参考音频文字固定在 config.py 里，前端不再提供编辑入口
    prompt = SOVITS_PROMPT_TEXT

    with db() as conn:
        exists = conn.execute(
            "SELECT api_key FROM user_tts_settings WHERE user_id = ?", (user["id"],)
        ).fetchone()
        # 留空表示"不改 Key"，只改模型/音色
        key = new_key or (exists["api_key"] if exists else "")

        conn.execute(
            """
            INSERT INTO user_tts_settings (user_id, api_key, model, voice, prompt_text, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                api_key     = excluded.api_key,
                model       = excluded.model,
                prompt_text = excluded.prompt_text,
                updated_at  = excluded.updated_at
            """,
            (user["id"], key, model, DEFAULT_VOICE, prompt),
        )

    return {
        "ok": True,
        "has_key": bool(key),
        "key_masked": mask_key(key) if key else "",
        "prompt_text": prompt,
    }


@router.post("/speak")
async def speak(body: SpeakIn, user: dict = Depends(current_user)):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "要朗读的文本是空的")

    settings = _settings_of(user["id"])

    # 1) 优先用本地的芙宁娜音色（GPT-SoVITS）
    try:
        audio = await synthesize_local(text, settings.get("prompt_text", ""))
        return Response(
            content=audio,
            media_type="audio/wav",
            headers={"Cache-Control": "no-store"},
        )
    except SovitsError as local_error:
        # 没配云端 Key 就把本地失败的原因直接告诉前端
        if not settings["api_key"]:
            raise HTTPException(503, str(local_error)) from local_error

        # 2) 本地服务没起来时，退回云端 Qwen-TTS
        try:
            audio = await synthesize(
                text, settings["api_key"], settings["model"], DEFAULT_VOICE
            )
        except TtsError as exc:
            raise HTTPException(502, f"{local_error}；云端合成也失败：{exc}") from exc

        return Response(
            content=audio,
            media_type="audio/wav",
            headers={"Cache-Control": "no-store"},
        )