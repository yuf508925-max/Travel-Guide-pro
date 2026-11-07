# =====================================================================
# providers/deepseek.py —— DeepSeek 的 AI 调用层
#   只负责「把历史+新消息丢给模型，逐段吐回文字」，
#   不碰 HTTP、不碰 SSE 格式（那是 routers 的事）。
#   以后要换供应商，照着这个文件的接口再写一个就行。
# =====================================================================

from openai import AsyncOpenAI

from ..config import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, MAX_TOKENS, TEMPERATURE

# DeepSeek 的接口是 OpenAI 兼容格式，所以直接用官方 SDK 连
# （openai>=1.x 的 AsyncOpenAI 支持异步 + 流式）
#
# 为什么要按（地址 + Key）缓存客户端？
#   每个账号可以在「设置」里填多套自己的 Key / Base URL（存在 user_providers 表），
#   不同的 Key 或不同的中转地址都必须用不同的客户端，否则会互相覆盖。
#   Key 只来自用户配置，没有任何 Key 时直接报错提示去设置里填。
_clients: dict[tuple[str, str], AsyncOpenAI] = {}


def _client_for(api_key: str | None, base_url: str | None = None) -> AsyncOpenAI:
    """取一个可用的客户端（Key 只能是用户自己在「设置」里填的）"""
    key = (api_key or "").strip()
    url = (base_url or "").strip() or DEEPSEEK_BASE_URL
    if not key:
        raise RuntimeError("还没有可用的 API Key：点右上角「设置」→「添加模型提供商」填一套")

    cache_key = (url, key)
    client = _clients.get(cache_key)
    if client is None:
        client = AsyncOpenAI(api_key=key, base_url=url)
        _clients[cache_key] = client
    return client


def default_config() -> dict:
    """当前的默认配置（给设置接口展示「不填时会用什么」）"""
    return {"base_url": DEEPSEEK_BASE_URL, "model": DEEPSEEK_MODEL}


# ------------------------------------------------------------------
# 芙芙的人设提示词：想调语气、加规矩，改这里
# ------------------------------------------------------------------
SYSTEM_PROMPT = """你是原神游戏中的角色芙宁娜，一个活泼、贴心、略带俏皮的旅行向导。
- 用中文回答，语气轻松自然，可以可爱但别过度。
- 用户聊旅行规划时，主动问清：目的地、天数、预算、出行方式、偏好（美食/风景/人文/躺平）。
- 给建议要具体可执行：说得出地名、路线、大致花费、时间安排。
- 回答精炼，一般不超过 300 字，能用短句就别写长段。
- 不要自称“AI”或“语言模型”，你就是芙宁娜。"""


async def stream_chat(
    history: list[tuple[str, str]],
    user_text: str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
):
    """流式生成回复。

    参数：
        history   : [(role, text), ...]，role 为 'user' 或 'assistant'
        user_text : 用户这一轮说的话
        api_key   : 账号「设置」里那套 Key（没有就让上层报错）
        base_url  : 账号设置里的接口地址（可为空，空则用 config.py 的）
        model     : 账号设置里的模型名（可为空，空则用 config.py 的）
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

    model_name = (model or "").strip() or DEEPSEEK_MODEL
    client = _client_for(api_key, base_url)

    try:
        stream = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            stream=True,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
    except Exception as exc:
        # 把模型名带出来，前端报错时能一眼看出是哪套配置出的问题
        raise RuntimeError(f"模型 {model_name} 调用失败：{exc}") from exc

    async for chunk in stream:
        # 有的兼容接口会把错误塞在流里（HTTP 仍是 200），先看这个
        chunk_error = getattr(chunk, "error", None)
        if chunk_error:
            detail = chunk_error.get("message") if isinstance(chunk_error, dict) else str(chunk_error)
            raise RuntimeError(f"模型 {model_name} 返回错误：{detail}")

        # 有的 OpenAI 兼容接口（比如 dashscope 的某些模型）会在流末尾插入
        # 只带 usage / 不带 choices 的帧，直接 chunk.choices[0] 会 IndexError。
        choices = getattr(chunk, "choices", None)
        if not choices:
            continue

        delta = getattr(choices[0], "delta", None)
        if delta is None:
            continue

        # 推理模型会先吐思考过程（reasoning_content），再吐正文（content）。
        # 两者必须分开推给前端，否则思考那几秒前端收不到任何字。
        thinking = getattr(delta, "reasoning_content", None)
        content = getattr(delta, "content", None)
        if thinking:
            yield ("thinking", thinking)
        if content:
            yield ("text", content)


async def aclose():
    """关闭所有底层 HTTP 连接，在 app 生命周期结束时调用"""
    for client in _clients.values():
        await client.close()
    _clients.clear()
