# =====================================================================
# providers/deepseek.py —— DeepSeek 的 AI 调用层
#   只负责「把历史+新消息丢给模型，逐段吐回文字」，
#   不碰 HTTP、不碰 SSE 格式（那是 routers 的事）。
#   以后要换供应商，照着这个文件的接口再写一个就行。
# =====================================================================

from openai import AsyncOpenAI

from ..config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    MAX_TOKENS,
    TEMPERATURE,
)

# DeepSeek 的接口是 OpenAI 兼容格式，所以直接用官方 SDK 连
# （openai>=1.x 的 AsyncOpenAI 支持异步 + 流式）
_client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


# ------------------------------------------------------------------
# 芙芙的人设提示词：想调语气、加规矩，改这里
# ------------------------------------------------------------------
SYSTEM_PROMPT = """你是原神游戏中的角色芙宁娜，一个活泼、贴心、略带俏皮的旅行向导。
- 用中文回答，语气轻松自然，可以可爱但别过度。
- 用户聊旅行规划时，主动问清：目的地、天数、预算、出行方式、偏好（美食/风景/人文/躺平）。
- 给建议要具体可执行：说得出地名、路线、大致花费、时间安排。
- 回答精炼，一般不超过 300 字，能用短句就别写长段。
- 不要自称“AI”或“语言模型”，你就是芙宁娜。"""


async def stream_chat(history: list[tuple[str, str]], user_text: str):
    """流式生成回复。

    参数：
        history   : [(role, text), ...]，role 为 'user' 或 'assistant'
        user_text : 用户这一轮说的话
    产出：
        (kind, text) —— kind 有三类：
          'status'   : 'thinking'，表示开始思考（让前端立刻有反馈，别干等）
          'thinking' : 模型的思考过程片段（推理模型才有，默认不展示）
          'text'     : 正式正文片段，拼起来就是完整回复
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": role, "content": text} for role, text in history]
    messages.append({"role": "user", "content": user_text})

    # 先发一帧状态：模型思考的那几秒，前端才不会是一片空白
    yield ("status", "thinking")

    stream = await _client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=messages,
        stream=True,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta
        # 推理模型会先吐思考过程（reasoning_content），再吐正文（content）。
        # 两者必须分开推给前端，否则思考那几秒前端收不到任何字。
        thinking = getattr(delta, "reasoning_content", None)
        content = getattr(delta, "content", None)
        if thinking:
            yield ("thinking", thinking)
        if content:
            yield ("text", content)


async def aclose():
    """关闭底层 HTTP 连接，在 app 生命周期结束时调用"""
    await _client.close()
