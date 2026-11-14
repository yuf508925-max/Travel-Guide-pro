# =====================================================================
# providers/deepseek.py —— DeepSeek 的 AI 调用层
#   只负责「把历史+新消息丢给模型，逐段吐回文字」，
#   不碰 HTTP、不碰 SSE 格式（那是 routers 的事）。
#   以后要换供应商，照着这个文件的接口再写一个就行。
# =====================================================================

import asyncio
import json
import re

from openai import AsyncOpenAI

from ..config import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, MAX_TOKENS, TEMPERATURE
from ..llm_trace import Timer, record

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
- 不要自称“AI”或“语言模型”，你就是芙宁娜。
- 你有查天气、查火车班次、算路线三个工具。问到天气、车次、两地多远/要开多久时，
  先调工具拿真实数据再说，不要凭印象编数字；工具报错就把原因用你自己的话讲给用户。
- 别为了凑数据把三个工具都调一遍，只调真正用得上的那个。"""


# 一次对话里最多允许多少轮「模型要工具 → 我们给结果」。
# 3 轮够用了（查天气 + 查车次 + 再补一条），多了既慢又贵。
MAX_TOOL_ROUNDS = 3


async def _stream_once(
    client,
    model_name: str,
    messages: list[dict],
    tools: list[dict] | None,
    sink: dict,
):
    """跑一次模型流：正文 / 思考过程往外吐，工具调用攒进 sink

    sink 是个可变 dict（{"text": [...], "thinking": [...], "calls": {...}}），
    因为生成器没法 return 值，只能靠它把这一轮的结果带出去。
    """
    kwargs = {
        "model": model_name,
        "messages": messages,
        "stream": True,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    stream = await client.chat.completions.create(**kwargs)

    async for chunk in stream:
        # 有的兼容接口会把错误塞在流里（HTTP 仍是 200），先看这个
        chunk_error = getattr(chunk, "error", None)
        if chunk_error:
            detail = chunk_error.get("message") if isinstance(chunk_error, dict) else str(chunk_error)
            raise RuntimeError(f"模型 {model_name} 返回错误：{detail}")

        choices = getattr(chunk, "choices", None)
        if not choices:
            continue

        delta = getattr(choices[0], "delta", None)
        if delta is None:
            continue

        # 推理模型会先吐思考过程（reasoning_content），再吐正文（content）。
        thinking = getattr(delta, "reasoning_content", None)
        content = getattr(delta, "content", None)
        if thinking:
            sink["thinking"].append(thinking)
            yield ("thinking", thinking)
        if content:
            sink["text"].append(content)
            yield ("text", content)

        # 工具调用是分片来的：name 一般一次给全，arguments 要一段段拼
        for call in getattr(delta, "tool_calls", None) or []:
            index = getattr(call, "index", 0) or 0
            slot = sink["calls"].setdefault(
                index, {"id": "", "name": "", "arguments": ""}
            )
            call_id = getattr(call, "id", None)
            if call_id:
                slot["id"] = call_id
            function = getattr(call, "function", None)
            if function is not None:
                name = getattr(function, "name", None)
                arguments = getattr(function, "arguments", None)
                if name:
                    slot["name"] = name
                if arguments:
                    slot["arguments"] += arguments


async def stream_chat(
    history: list[tuple[str, str]],
    user_text: str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    memory: str = "",
    tools: list[dict] | None = None,
    tool_executor=None,
):
    """流式生成回复。

    参数：
        history   : [(role, text), ...]，role 为 'user' 或 'assistant'
        user_text : 用户这一轮说的话
        api_key   : 账号「设置」里那套 Key（没有就让上层报错）
        base_url  : 账号设置里的接口地址（可为空，空则用 config.py 的）
        model     : 账号设置里的模型名（可为空，空则用 config.py 的）
    产出：
        (kind, text) —— kind 有四类：
          'status'   : 'thinking'，表示开始思考（让前端立刻有反馈，别干等）
          'thinking' : 模型的思考过程片段（推理模型才有，默认不展示）
          'text'     : 正式正文片段，拼起来就是完整回复
          'tool'     : 工具调用进度（JSON 字符串：{status, name, ok, error}）
    """
    system = SYSTEM_PROMPT
    if memory.strip():
        # 这段摘要只属于「当前这个对话」，换对话就换一套记忆
        system += (
            "\n\n【这段对话之前聊过的内容（供你延续上下文，不要复述给用户）】\n"
            + memory.strip()
        )

    messages = [{"role": "system", "content": system}]
    messages += [{"role": role, "content": text} for role, text in history]
    messages.append({"role": "user", "content": user_text})

    # 先发一帧状态：模型思考的那几秒，前端才不会是一片空白
    yield ("status", "thinking")

    model_name = (model or "").strip() or DEEPSEEK_MODEL
    client = _client_for(api_key, base_url)
    trace_url = (base_url or "").strip() or DEEPSEEK_BASE_URL

    timer = Timer()
    timer.__enter__()
    collected: list[str] = []
    error_text = ""

    try:
        # 可以多轮：模型先要工具 → 我们执行 → 把结果喂回去 → 它再决定要不要继续要
        for round_index in range(MAX_TOOL_ROUNDS + 1):
            # 最后一轮不再给工具，逼它必须给出文字回复，别一直查下去
            allow_tools = tools if (tools and tool_executor and round_index < MAX_TOOL_ROUNDS) else None

            sink = {"text": [], "thinking": [], "calls": {}}
            try:
                async for event in _stream_once(client, model_name, messages, allow_tools, sink):
                    if event[0] == "text":
                        collected.append(event[1])
                    yield event
            except Exception as exc:
                # 有些兼容接口不支持 tools 参数：没吐出任何东西时降级成普通聊天重试一次
                if allow_tools and not sink["text"] and not sink["calls"]:
                    allow_tools = None
                    sink = {"text": [], "thinking": [], "calls": {}}
                    async for event in _stream_once(client, model_name, messages, None, sink):
                        if event[0] == "text":
                            collected.append(event[1])
                        yield event
                elif isinstance(exc, RuntimeError):
                    raise
                else:
                    # 把模型名带出来，前端报错时能一眼看出是哪套配置出的问题
                    raise RuntimeError(f"模型 {model_name} 调用失败：{exc}") from exc

            calls = [call for call in sink["calls"].values() if call["name"]]
            if not calls or not allow_tools:
                break

            # 1) 先把「模型要调这些工具」这一条助手消息写回历史（OpenAI 协议要求）
            tool_messages = []
            for position, call in enumerate(calls):
                call_id = call["id"] or f"call_{round_index}_{position}"
                call["id"] = call_id
                tool_messages.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": call["arguments"] or "{}",
                        },
                    }
                )
            messages.append(
                {
                    "role": "assistant",
                    "content": "".join(sink["text"]),
                    "tool_calls": tool_messages,
                }
            )

            # 2) 逐个执行，并把结果作为 role=tool 的消息喂回去
            for call in calls:
                payload = json.dumps(
                    {"status": "start", "name": call["name"]}, ensure_ascii=False
                )
                yield ("tool", payload)

                result = await tool_executor(call["name"], call["arguments"])
                ok = bool(result.get("ok"))
                error = "" if ok else str(result.get("error") or "工具调用失败")
                yield (
                    "tool",
                    json.dumps(
                        {
                            "status": "done",
                            "name": call["name"],
                            "ok": ok,
                            "error": error,
                        },
                        ensure_ascii=False,
                    ),
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        # 工具结果可能很长，截一下：模型只需要关键字段
                        "content": json.dumps(result, ensure_ascii=False)[:4000],
                    }
                )
    except Exception as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        # 监控用：不管成功、报错还是前端中途断开，都把这一轮完整对话记下来
        timer.__exit__()
        record(
            "chat",
            model_name,
            messages,
            response="".join(collected),
            error=error_text,
            ms=timer.ms,
            base_url=trace_url,
        )


async def aclose():
    """关闭所有底层 HTTP 连接，在 app 生命周期结束时调用"""
    for client in _clients.values():
        await client.close()
    _clients.clear()


# ------------------------------------------------------------------
# 摘要：关闭网页时把整段对话压缩成一小段记忆
# ------------------------------------------------------------------
SUMMARY_PROMPT = """你在帮一个旅行助手整理「对话记忆」。请输出一个 JSON 对象（不要 markdown 代码块），格式：
{"summary": "不超过 200 字的中文摘要", "memories": [{"kind": "fact|preference|plan|place|event", "content": "一句话"}]}

要求：
- summary：第三人称陈述句，只保留对后续对话有用的信息（目的地、天数、预算、同行人、口味/偏好、已定的计划、明确不要的东西）。不要寒暄、不要复述原话、不要分点。
- memories：3~8 条结构化记忆，每条 20 字以内的一件「事实」。kind 含义：
  · fact       客观事实（去哪、几个人、什么时候）
  · preference 偏好 / 雷点（爱吃什么、不想爬山）
  · plan       已经定下的安排
  · place      明确提到并想去的具体地点
  · event      发生过的事（订了票、改过日期）
- 如果这段对话没有实质内容（只是打招呼），summary 写「（这段对话没有实质内容）」，memories 给空数组 []。
- 只输出 JSON，不要解释。"""

MEMORY_KINDS = {"fact", "preference", "plan", "place", "event"}


async def summarize_chat(
    transcript: str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    memory: str = "",
) -> dict:
    """把对话文本压成「摘要 + 结构化记忆」（非流式，一次请求）

    返回 {"summary": str, "memories": [{"kind": str, "content": str}]}
    """
    client = _client_for(api_key, base_url)
    user_text = transcript[:12000]
    if memory.strip():
        user_text = (
            "【之前的记忆，新的内容要和它合并，不要重复】\n"
            + memory.strip()[:800]
            + "\n\n【新的一段对话】\n"
            + user_text
        )

    summary_messages = [
        {"role": "system", "content": SUMMARY_PROMPT},
        {"role": "user", "content": user_text},
    ]
    trace_url = (base_url or "").strip() or DEEPSEEK_BASE_URL
    timer = Timer()
    timer.__enter__()
    try:
        resp = await client.chat.completions.create(
            model=model or DEEPSEEK_MODEL,
            temperature=0.3,
            max_tokens=2000,   # 推理模型会先花 token 想，给小了正文就空了
            messages=summary_messages,
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        timer.__exit__()
        record(
            "summary",
            model or DEEPSEEK_MODEL,
            summary_messages,
            error=f"{type(exc).__name__}: {exc}",
            ms=timer.ms,
            base_url=trace_url,
        )
        raise
    else:
        timer.__exit__()
        record(
            "summary",
            model or DEEPSEEK_MODEL,
            summary_messages,
            response=raw,
            ms=timer.ms,
            base_url=trace_url,
        )

    # 模型有时候会把 JSON 包在 ```json ... ``` 里
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    def _parse(text: str):
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        # 模型偶尔会在 JSON 前后加解释文字，掐头去尾再试
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        # strict=False：允许字符串里出现裸换行/制表符（模型偶尔会这么写）
        return json.loads(text, strict=False)

    try:
        data = _parse(raw)
    except Exception as exc:
        # 解析不了就退化成纯摘要，至少别丢信息
        return {"summary": raw[:600], "memories": [], "parse_error": repr(exc)}

    summary = str(data.get("summary") or "").strip()[:600]
    memories: list[dict] = []
    for item in data.get("memories") or []:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        kind = str(item.get("kind") or "fact").strip().lower()
        if kind not in MEMORY_KINDS:
            kind = "fact"
        memories.append({"kind": kind, "content": content[:120]})
        if len(memories) >= 12:
            break

    return {"summary": summary, "memories": memories}


# ------------------------------------------------------------------
# AI 控制 Live2D：让大模型看着芙芙刚说的话，挑一个表情/动作
# ------------------------------------------------------------------
# 清单必须和后端 / 前端保持一致：
#   动作组来自 model3.json 的 Motions（4 个），表情来自 Expressions（14 个，
#   鱼鱼 / 汗 已按需求删掉）。
#   这里不放宽范围，免得模型编出一个不存在的表情名，前端 setExpression 静默失败。
LIVE2D_MOTIONS = {
    "Idle": "待机：平静、温柔、日常说话时用",
    "TapBody": "摊手：无奈、解释、耸肩、开玩笑",
    "变芒": "变芒：切成「芒」形态，情绪高涨、得意、闪闪发光",
    "变荒": "变荒：切成「荒」形态，低落、认真、气氛沉下来",
}

LIVE2D_EXPRESSIONS = [
    "呆毛电风扇", "哭", "喝饮料", "大聪明",
    "小脸红", "帽子", "托脸", "拿勺子",
    "拿蛋糕", "捂嘴", "星星",
    "猫猫嘴", "生气", "走路切换",
]

LIVE2D_ACT_PROMPT = """你是芙宁娜的舞台监督。你会看到最近一段对话，请替她挑一个最合适的动作和一个表情，让她的表演跟对话内容对得上。

【动作】（最多选一个）
- Idle：待机，平静/温柔地说话时用（大多数时候都是它）
- TapBody：摊手，无奈、解释、耸肩、开玩笑时用
- 变芒：切换成「芒」形态，情绪高涨、得意、闪闪发光时用
- 变荒：切换成「荒」形态，情绪低落、认真、气氛沉下来时用

【表情】（最多选一个）
呆毛电风扇、哭、喝饮料、大聪明、小脸红、帽子、托脸、拿勺子、拿蛋糕、捂嘴、星星、猫猫嘴、生气、走路切换

【两种场合】
- 有台词：按她刚说的这句话挑，情绪明显时才演。
- 挂机（她这会儿没有说话，安静待着）：按最近聊的内容挑一个她此刻自然的小表情，动作一般给 Idle；不要挑变芒/变荒这类大动作，除非刚才聊的正好是让人得意或低落的事。

【规矩】
- 大部分时候用 Idle，再配一个温和的表情就够了，别每句都演。
- 结合上下文看整体气氛，不要只看最后一句话；但也别重复上一轮已经用过的表情。
- 拿不准就把 motion 或 expression 写成 null。
- 只输出 JSON，不要 markdown 代码块，不要解释：
{"motion": "TapBody", "expression": "小脸红", "reason": "十个字以内的理由"}"""

# 中文标签 / 大小写变体 → 模型里真正的组名
_LIVE2D_MOTION_ALIASES = {
    "idle": "Idle",
    "待机": "Idle",
    "tapbody": "TapBody",
    "tap_body": "TapBody",
    "摊手": "TapBody",
    "变芒": "变芒",
    "芒": "变芒",
    "变荒": "变荒",
    "荒": "变荒",
}


def _loads_json(raw: str) -> dict:
    """模型爱把 JSON 包在 ```json 里、或前后加两句解释，这里都顺着它来"""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text, strict=False)


def normalize_live2d_action(data: dict) -> dict:
    """把模型吐的东西收敛到「真实存在的动作组 + 表情」上"""
    motion_raw = str(data.get("motion") or "").strip()
    motion = _LIVE2D_MOTION_ALIASES.get(motion_raw.lower(), motion_raw) or None
    if motion not in LIVE2D_MOTIONS:
        motion = None

    expression = str(data.get("expression") or "").strip()
    if expression not in LIVE2D_EXPRESSIONS:
        expression = None

    return {
        "motion": motion,
        "expression": expression,
        "reason": str(data.get("reason") or "").strip()[:60],
    }


async def choose_live2d_action(
    reply: str = "",
    user_text: str = "",
    history: list[dict] | None = None,
    idle: bool = False,
    previous: dict | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> dict:
    """结合最近的对话，挑一个表情/动作（非流式，一次请求）

    reply  芙芙这一轮说的话；挂机时为空
    history 当前对话最近几条消息 [{"role": "user"|"ai", "text": ...}]，
            只由前端传「正在看的那条对话」，不会串到别的对话
    idle   挂机时她没说话，按上下文挑个自发的小表情
    previous 这条对话上一轮演过的 {motion, expression}，用来避免连着两轮同一个表情
            （不给它这个信息时，模型会一直挑同一个，看起来就像"表情不换了"）

    返回 {"motion": str|None, "expression": str|None, "reason": str}
    注意：这里不吞异常，让路由层决定是报错还是静默返回空动作。
    """
    client = _client_for(api_key, base_url)

    lines = []
    turns = []
    for item in (history or [])[-8:]:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        who = "用户" if str(item.get("role")) == "user" else "芙芙"
        turns.append(f"{who}：{text[:300]}")
    if turns:
        lines.append("【最近的对话】\n" + "\n".join(turns))

    if idle:
        lines.append(
            "【此刻】芙芙没有说话，正安静待着。"
            "请按上面的对话挑一个她此时自然的小表情；动作一般给 Idle。"
        )
    else:
        if user_text.strip():
            lines.append("【用户刚说的话】\n" + user_text.strip()[:400])
        lines.append("【芙芙的回复】\n" + reply.strip()[:1200])

    lines.append("请按规矩挑动作和表情，只输出 JSON。")

    # 上一轮演过什么：不告诉模型，它会连着挑同一个表情（实测连着两轮"猫猫嘴"）
    prev_expression = str((previous or {}).get("expression") or "").strip()
    prev_motion = str((previous or {}).get("motion") or "").strip()
    if prev_expression or prev_motion:
        picked = []
        if prev_motion:
            picked.append(f"动作「{prev_motion}」")
        if prev_expression:
            picked.append(f"表情「{prev_expression}」")
        lines.append(
            "【上一轮你选的】" + "、".join(picked)
            + "。这一轮请换一个不一样的表情（除非完全重复才合适，那就换个动作）。"
        )

    base_user = "\n\n".join(lines)
    trace_url = (base_url or "").strip() or DEEPSEEK_BASE_URL
    kind = "live2d" + ("-idle" if idle else "")

    async def _ask(hint: str, temperature: float) -> dict:
        """问一次，返回收敛后的动作；每次调用都记进监控日志"""
        content = base_user if not hint else base_user + "\n\n" + hint
        msgs = [
            {"role": "system", "content": LIVE2D_ACT_PROMPT},
            {"role": "user", "content": content},
        ]
        timer = Timer()
        timer.__enter__()
        try:
            resp = await client.chat.completions.create(
                model=model or DEEPSEEK_MODEL,
                # 挂机/重试时放开一点温度，不然每次都是同一个表情
                temperature=temperature,
                # 推理模型会先花 token 思考，给小了正文就是空的（挑表情不需要长回复，但得留够）
                max_tokens=800,
                messages=msgs,
            )
            raw = (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            timer.__exit__()
            record(
                kind,
                model or DEEPSEEK_MODEL,
                msgs,
                error=f"{type(exc).__name__}: {exc}",
                ms=timer.ms,
                base_url=trace_url,
            )
            raise
        timer.__exit__()
        record(
            kind,
            model or DEEPSEEK_MODEL,
            msgs,
            response=raw,
            ms=timer.ms,
            base_url=trace_url,
        )
        try:
            return normalize_live2d_action(_loads_json(raw))
        except Exception:
            # 解析不了就什么都不做，别因为挑表情失败把一脸表情换乱
            return {"motion": None, "expression": None, "reason": ""}

    action = await _ask("", 0.75 if idle else 0.4)

    # 两种情况再问一次：① 又挑了跟上一轮一模一样的；② 干脆没给出可用结果
    repeat = bool(
        not idle
        and prev_expression
        and action["expression"] == prev_expression
        and (action["motion"] or "") == (prev_motion or "")
    )
    empty = not action["motion"] and not action["expression"]
    if repeat or (empty and not idle):
        if repeat:
            hint = (
                f"【上一轮的「{prev_expression}」刚用过】这次必须换一个完全不同的表情，"
                "动作也可以跟着变。"
            )
        else:
            hint = "【上一次的回答没有给出可用 JSON】这次严格只输出那个 JSON，不要任何解释。"
        try:
            retry = await _ask(hint, 0.95)
        except Exception:
            retry = None
        if retry:
            retry_ok = bool(retry["motion"] or retry["expression"])
            retry_differs = retry["expression"] != prev_expression or not prev_expression
            if retry_ok and retry_differs:
                action = retry
            elif retry_ok and empty:
                action = retry

    return action


# ---------------------------------------------------------------------
# B站旅行 vlog：让模型把「地区」变成几条像真人会敲进搜索框的关键词
#   为什么不直接把「青岛」丢给 B 站搜？
#     搜「青岛」出来的多半是新闻、航拍、房地产；搜「青岛 旅行 vlog」
#     才是真的旅行记录。模型这一步只干一件事：想词。
# ---------------------------------------------------------------------
VLOG_KEYWORD_PROMPT = """你是旅行视频的搜索助手。用户会给你一个地区（城市 / 景区 / 国家 / 地区名）。

请给出 3 条用于在 B 站搜索「该地区旅行 vlog」的中文关键词。

要求：
- 每条 2~12 个字，像真人会敲进 B 站搜索框那样自然；
- 三条角度尽量不同（比如：城市+旅行vlog、城市+旅游攻略、景点+实拍/美食/一日游）；
- 地区名原样保留，不要换成别的城市，也不要加书名号、引号、序号、标点；
- 不要写「视频」「推荐」这类废话词堆砌。

只输出 JSON，不要解释：
{"keywords": ["关键词1", "关键词2", "关键词3"]}"""


def _extract_keywords(raw: str, limit: int = 3) -> list[str]:
    """从模型输出里抠出关键词列表：正常是 JSON，抽风时按行/逗号兜底"""
    text = (raw or "").strip()
    candidates: list[str] = []

    try:
        data = _loads_json(text)
        if isinstance(data, dict):
            value = data.get("keywords") or data.get("keyword") or []
            if isinstance(value, str):
                candidates = [value]
            elif isinstance(value, list):
                candidates = [str(v) for v in value]
    except Exception:
        candidates = []

    if not candidates:
        # 兜底：去掉 JSON 符号后按换行 / 逗号 / 顿号切
        cleaned = text.replace("{", " ").replace("}", " ").replace("[", " ").replace("]", " ")
        cleaned = cleaned.replace("keywords", " ").replace("：", ":").replace('"', " ")
        for piece in re.split(r"[\n,，、;；]+", cleaned):
            piece = piece.split(":", 1)[-1].strip(" -·*")
            if piece:
                candidates.append(piece)

    out: list[str] = []
    for item in candidates:
        word = str(item).strip().strip("「」『』\"'《》")
        word = re.sub(r"^\d+[.、)]\s*", "", word)   # 去掉 "1. " 这种序号
        if not (2 <= len(word) <= 20):
            continue
        if word in out:
            continue
        out.append(word)
        if len(out) >= limit:
            break
    return out


async def suggest_vlog_keywords(
    region: str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    limit: int = 3,
) -> list[str]:
    """地区 → B 站搜索关键词（失败返回空列表，调用方自己兜底）"""
    name = (region or "").strip()
    if not name:
        return []

    client = _client_for(api_key, base_url)
    model_name = model or DEEPSEEK_MODEL
    messages = [
        {"role": "system", "content": VLOG_KEYWORD_PROMPT},
        {"role": "user", "content": f"地区：{name}"},
    ]
    trace_url = (base_url or "").strip() or DEEPSEEK_BASE_URL

    timer = Timer()
    timer.__enter__()
    try:
        resp = await client.chat.completions.create(
            model=model_name,
            temperature=0.8,
            max_tokens=600,
            messages=messages,
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        timer.__exit__()
        record(
            "vlog",
            model_name,
            messages,
            error=f"{type(exc).__name__}: {exc}",
            ms=timer.ms,
            base_url=trace_url,
        )
        raise
    timer.__exit__()
    record("vlog", model_name, messages, response=raw, ms=timer.ms, base_url=trace_url)
    return _extract_keywords(raw, limit)

