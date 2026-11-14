# =====================================================================
# llm_monitor.py —— 独立端口的「后端 ↔ 大模型」对话监控台
# ---------------------------------------------------------------------
# 和主服务完全分开跑，不占 8000 那个端口，也不需要登录：
#     python server/llm_monitor.py            # 默认 http://127.0.0.1:8124
#     python server/llm_monitor.py --port 8300
#
# 数据来自 server/logs/llm_trace.jsonl（由 server/llm_trace.py 写入）。
# 每次模型调用结束后主服务追加一行，这里轮询这个文件并按时间顺序展示：
# 请求里的 system / 用户 / 助手消息、模型最终回复、错误、耗时、模型名和接口地址。
#
# 只用标准库，没有任何依赖，主服务停着也能看历史记录。
# =====================================================================

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

LOG_FILE = Path(__file__).resolve().parent / "logs" / "llm_trace.jsonl"

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>芙芙后端 · 大模型对话监控</title>
<style>
  :root {
    --bg: #0f1115; --panel: #171a21; --line: #262b36;
    --text: #e6e9ef; --muted: #8b93a5; --accent: #6aa9ff;
    --user: #7dd3a0; --assistant: #c792ea; --system: #8b93a5;
    --err: #ff6b6b;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 13px/1.55 "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
  }
  header {
    position: sticky; top: 0; z-index: 10; background: rgba(15,17,21,.92);
    backdrop-filter: blur(8px); border-bottom: 1px solid var(--line);
    padding: 10px 16px; display: flex; gap: 14px; align-items: center; flex-wrap: wrap;
  }
  header h1 { font-size: 14px; margin: 0 10px 0 0; font-weight: 600; letter-spacing: .3px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #37d67a; display: inline-block; margin-right: 6px; }
  .dot.off { background: #555c6b; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .chip {
    border: 1px solid var(--line); background: transparent; color: var(--muted);
    border-radius: 999px; padding: 3px 11px; cursor: pointer; font-size: 12px;
  }
  .chip.on { border-color: var(--accent); color: var(--accent); background: rgba(106,169,255,.1); }
  .spacer { flex: 1; }
  .meta { color: var(--muted); font-size: 12px; }
  main { padding: 14px 16px 40px; max-width: 1100px; margin: 0 auto; }
  .empty { color: var(--muted); text-align: center; padding: 60px 0; line-height: 2; }
  .card {
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    margin-bottom: 12px; overflow: hidden;
  }
  .card.err { border-color: rgba(255,107,107,.45); }
  .card__head {
    display: flex; gap: 10px; align-items: center; padding: 8px 12px;
    border-bottom: 1px solid var(--line); cursor: pointer; user-select: none;
  }
  .badge {
    font-size: 11px; padding: 2px 8px; border-radius: 6px;
    background: rgba(106,169,255,.16); color: var(--accent); white-space: nowrap;
  }
  .badge.summary { background: rgba(255,196,87,.15); color: #ffc457; }
  .badge.live2d { background: rgba(199,146,234,.16); color: var(--assistant); }
  .badge.live2d-idle { background: rgba(125,211,160,.15); color: var(--user); }
  .card__head .model { font-weight: 600; }
  .card__head .time { color: var(--muted); }
  .card__head .ms { color: var(--muted); margin-left: auto; }
  .card__body { padding: 10px 12px; display: block; }
  .card.collapsed .card__body { display: none; }
  .msg { margin: 0 0 9px; }
  .msg:last-child { margin-bottom: 0; }
  .role { font-size: 11px; letter-spacing: .5px; text-transform: uppercase; margin-bottom: 2px; }
  .role.user { color: var(--user); }
  .role.assistant { color: var(--assistant); }
  .role.system { color: var(--system); }
  .content {
    white-space: pre-wrap; word-break: break-word;
    background: #11141a; border: 1px solid #1e232d; border-radius: 6px;
    padding: 7px 9px; max-height: 260px; overflow: auto;
  }
  .resp .content { border-color: rgba(106,169,255,.28); }
  .errbox { color: var(--err); white-space: pre-wrap; }
  .tags { color: var(--muted); font-size: 11px; margin-top: 8px; word-break: break-all; }
</style>
</head>
<body>
<header>
  <h1><span class="dot" id="dot"></span>后端 ↔ 大模型 对话监控</h1>
  <div class="chips" id="chips"></div>
  <div class="spacer"></div>
  <span class="meta" id="meta">等待数据…</span>
  <button class="chip" id="pauseBtn">暂停</button>
  <button class="chip" id="clearBtn">清屏</button>
  <button class="chip" id="stickBtn">自动滚到底: 开</button>
</header>
<main id="list"><div class="empty">还没有调用记录。<br />在页面上聊一句、或等挂机的 60 秒触发一次，这里就会出现请求和回复。</div></main>

<script>
const KINDS = [
  { key: 'all', label: '全部' },
  { key: 'chat', label: '聊天' },
  { key: 'live2d', label: '表情动作' },
  { key: 'live2d-idle', label: '挂机表情' },
  { key: 'summary', label: '记忆摘要' },
];
const LABEL = Object.fromEntries(KINDS.map(k => [k.key, k.label]));
const state = { kind: 'all', paused: false, stick: true, hiddenBefore: 0, items: [], cards: new Map() };

const chipsEl = document.getElementById('chips');
for (const k of KINDS) {
  const b = document.createElement('button');
  b.className = 'chip' + (k.key === state.kind ? ' on' : '');
  b.textContent = k.label;
  b.onclick = () => {
    state.kind = k.key;
    [...chipsEl.children].forEach((c, i) => c.classList.toggle('on', KINDS[i].key === k.key));
    renderList();
  };
  chipsEl.appendChild(b);
}

document.getElementById('pauseBtn').onclick = (e) => {
  state.paused = !state.paused;
  e.target.textContent = state.paused ? '继续' : '暂停';
  e.target.classList.toggle('on', state.paused);
};
document.getElementById('stickBtn').onclick = (e) => {
  state.stick = !state.stick;
  e.target.textContent = '自动滚到底: ' + (state.stick ? '开' : '关');
  e.target.classList.toggle('on', state.stick);
  if (state.stick) window.scrollTo(0, document.body.scrollHeight);
};
document.getElementById('clearBtn').onclick = () => {
  state.hiddenBefore = state.items.length ? state.items[state.items.length - 1].id : 0;
  renderList();
};

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

function buildCard(item) {
  const card = el('div', 'card' + (item.error ? ' err' : ''));
  const head = el('div', 'card__head');
  head.appendChild(el('span', 'badge ' + item.kind, LABEL[item.kind] || item.kind));
  head.appendChild(el('span', 'model', item.model || '未知模型'));
  head.appendChild(el('span', 'time', item.ts || ''));
  head.appendChild(el('span', 'ms', item.ms ? item.ms + ' ms' : ''));
  head.onclick = () => card.classList.toggle('collapsed');
  card.appendChild(head);

  const body = el('div', 'card__body');
  for (const m of item.messages || []) {
    const box = el('div', 'msg');
    box.appendChild(el('div', 'role ' + m.role, m.role));
    box.appendChild(el('div', 'content', m.content));
    body.appendChild(box);
  }
  if (item.response) {
    const box = el('div', 'msg resp');
    box.appendChild(el('div', 'role assistant', '响应'));
    box.appendChild(el('div', 'content', item.response));
    body.appendChild(box);
  }
  if (item.error) {
    const box = el('div', 'msg');
    box.appendChild(el('div', 'role', '错误'));
    box.appendChild(el('div', 'content errbox', item.error));
    body.appendChild(box);
  }
  if (item.base_url) body.appendChild(el('div', 'tags', item.kind + ' · ' + item.base_url));
  card.appendChild(body);
  return card;
}

function renderList() {
  const list = document.getElementById('list');
  const shown = state.items.filter(i => i.id > state.hiddenBefore && (state.kind === 'all' || i.kind === state.kind));
  list.innerHTML = '';
  if (!shown.length) {
    list.appendChild(el('div', 'empty', '这个分类下还没有记录。'));
    return;
  }
  for (const item of shown) list.appendChild(buildCard(item));
  if (state.stick) window.scrollTo(0, document.body.scrollHeight);
}

let timer = null;
async function poll() {
  if (state.paused) return;
  try {
    const res = await fetch('/api/traces', { cache: 'no-store' });
    const data = await res.json();
    document.getElementById('dot').className = 'dot';
    state.items = data.items || [];
    const total = state.items.length;
    const last = state.items[total - 1];
    document.getElementById('meta').textContent =
      total + ' 条记录' + (last ? ' · 最后一条 ' + last.ts : '');
    renderList();
  } catch (e) {
    document.getElementById('dot').className = 'dot off';
    document.getElementById('meta').textContent = '监控服务读不到日志：' + e.message;
  }
}
poll();
timer = setInterval(poll, 1500);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server 的命名约定
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/traces":
            limit = 200
            qs = parse_qs(parsed.query)
            if "limit" in qs:
                try:
                    limit = max(1, min(1000, int(qs["limit"][0])))
                except ValueError:
                    pass
            self._send(200, json.dumps({"items": read_traces(limit)}, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def log_message(self, fmt: str, *args) -> None:
        # 轮询很频繁，别把控制台刷满
        pass


def read_traces(limit: int) -> list[dict]:
    if not LOG_FILE.exists():
        return []
    try:
        with LOG_FILE.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-limit:]
    except OSError:
        return []

    items: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue   # 写到一半的行，下一轮就有了
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="后端 ↔ 大模型 对话监控台")
    parser.add_argument("--port", type=int, default=8124)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[llm-monitor] http://{args.host}:{args.port}  日志：{LOG_FILE}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
