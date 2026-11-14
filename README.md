# 旅行助手 · 芙宁娜 Live2D 数字人

一个带 Live2D 数字人（芙宁娜）的旅行助手：左边是能看、能说、会换表情的桌面宠物，右边是 AI 对话框。除了聊天，它还能查天气、规划行程、搜 B 站旅行 vlog、记长期记忆、放音乐、打电话（语音合成），后台还有一套管理面板。

---

## 一、这个项目由什么组成

| 部分 | 技术 | 位置 |
| --- | --- | --- |
| 前端 | Vue 3 + TypeScript + Vite | 项目根目录 / `src` |
| 后端 | Python FastAPI（uvicorn 常驻） | `server/` |
| 数据库 | SQLite 单文件 | `server/app.db`（首次启动自动建表） |
| Live2D | pixi.js 7 + pixi-live2d-display 0.5.0-beta | `src/components/Live2DStage.vue`，模型在 `public/芙宁娜（vts）/` |
| 语音合成 | GPT-SoVITS（本地推理服务，可选） | `voice-service/`，模型权重在 `models/Furina_GPT_SoVITS/` |
| 大模型监控台 | Python 标准库 HTTP 服务 | `server/llm_monitor.py`，端口 8124 |

功能一览：AI 对话（流式）、工具调用（查天气 / 查火车班次 / 算路线）、语音通话与口型同步、AI 自主表情动作（含挂机 60 秒自动换表情）、天气面板、行程规划（高德地图 JS API + 12306 车次）、B 站 vlog 搜索与浮窗播放器、记忆系统、音乐播放器（本地临时存储）、公告、用量统计与后台管理。

---

## 二、目录结构

```
vue-project/
├─ run.bat                  # 一键启动（语音 / 后端 / 监控台 / 前端 四个窗口）
├─ _voice.bat               # 启动 GPT-SoVITS 语音服务（9880）
├─ _api.bat                 # 启动后端（8000）
├─ _monitor.bat             # 启动大模型监控台（8124）
├─ _web.bat                 # 启动前端 dev server（5173）
├─ index.html
├─ vite.config.ts           # 端口 5173；把 /api 代理到 127.0.0.1:8000
├─ package.json             # 前端依赖与脚本
├─ src/                     # 前端源码
│  ├─ views/                # ChatView（主界面）/ LoginView / AdminView
│  ├─ components/           # Live2DStage、PhoneCall、WeatherPanel、RoutePlanner、
│  │                        # VlogPanel、VideoFloat、MemoryPanel、MusicPlayer、
│  │                        # AnnouncementPanel、SearchBar 等
│  ├─ composables/          # useChatStream、useLipSync、useLive2DActor、useAmap 等
│  └─ types/
├─ public/                  # 静态资源：Live2D 模型、背景视频、内置音乐
├─ server/                  # 后端源码
│  ├─ app.py                # FastAPI 入口，所有 router 在这里登记
│  ├─ config.py             # 全局常量（GPT-SoVITS 地址、模型默认值、CORS）
│  ├─ db.py                 # 建表 / 迁移 / 过期清理（sessions、usage_events 等）
│  ├─ security.py keyvault.py   # 密码哈希、用户 API Key 加密存储
│  ├─ routers/              # 各业务接口（chat、weather、routes、vlog、tts、music…）
│  ├─ providers/            # deepseek.py（大模型）、weather.py（天气数据源）
│  ├─ agent_tools.py        # 供大模型调用的工具：查天气 / 查火车 / 算路线
│  ├─ bilibili.py           # B 站搜索 / UP 主投稿 / 播放地址
│  ├─ train_check.py        # 12306 车次查询
│  ├─ music_store.py        # 上传音乐的落盘与清理
│  ├─ llm_trace.py          # 大模型请求追踪（写 JSONL）
│  ├─ llm_monitor.py        # 8124 监控台
│  ├─ requirements.txt      # 后端依赖
│  ├─ app.db                # SQLite 数据库（自动生成）
│  ├─ tmp_music/            # 上传的音乐（临时，随会话清理）
│  └─ logs/llm_trace.jsonl  # 监控台读的日志
├─ voice-service/           # GPT-SoVITS 本地语音服务
├─ models/Furina_GPT_SoVITS/# 语音模型权重与参考音频 ref.wav
└─ dist/                    # 前端打包产物（npm run build 生成）
```

---

## 三、环境要求

| 需要安装 | 版本 | 说明 |
| --- | --- | --- |
| Node.js | `^22.18.0` 或 `>=24.12.0` | 前端；低于这个版本 Vite 8 起不来 |
| Python | 3.10+（后端在 3.13 上验证） | 后端 `server/` |
| NVIDIA 显卡 + 驱动（可选） | CUDA 13.4（本项目实测环境） | 只有语音服务用；没有也能跑，只是没声音 |

---

## 四、安装依赖

源码、前端资源（Live2D 模型、背景、内置音乐）都已经在仓库里，**不需要另外下载**。需要装的只有下面这些（都在项目根目录 `vue-project/` 执行）。

### 1. 前端

```bash
npm install
```

### 2. 后端

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r server/requirements.txt
```

`server/requirements.txt`：`fastapi`、`uvicorn[standard]`、`openai`、`truststore`。

### 3. 语音服务（可选，需要 PyTorch + CUDA）

不用语音就跳过这节，聊天、天气、行程、vlog 都不受影响。

```bash
# 独立的 Python 3.11 环境
python -m venv voice-service\.venv-gsv
voice-service\.venv-gsv\Scripts\python.exe -m pip install --upgrade pip

# 先装 CUDA 版 PyTorch（默认 pypi 装的是 CPU 版；cu134 对应 CUDA 13.4，
# 换别的 CUDA 版本就把 cu134 改成 cu130 / cu126 等，驱动满足即可）
voice-service\.venv-gsv\Scripts\python.exe -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu134

# 再装推理依赖
voice-service\.venv-gsv\Scripts\python.exe -m pip install -r voice-service\requirements-min.txt
```

自检：`voice-service\.venv-gsv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"`，本项目实测输出 `2.15.0+cu134 13.4 True`。
没有显卡就把 `cu134` 换成 `cpu`，并把 `onnxruntime-gpu` 换成 `onnxruntime`。

### 4. 语音服务的模型和 ffmpeg 已经一起打包了

`models/`、`voice-service/GPT_SoVITS/pretrained_models/`、`voice-service/GPT_SoVITS/text/G2PWModel/`、`voice-service/ffmpeg-bin/` 都在项目里，不用另外下载：下完仓库、装完上面的依赖就能直接跑语音。

---

## 五、运行

### 方式 A：一键启动（推荐）

双击项目根目录的 **`run.bat`**，会依次弹出四个窗口：

1. `_voice.bat` → GPT-SoVITS 语音服务 `http://127.0.0.1:9880`（没装语音环境时这个窗口会报错，关掉即可）
2. `_api.bat` → 后端 `http://127.0.0.1:8000`
3. `_monitor.bat` → 大模型监控台 `http://127.0.0.1:8124`
4. `_web.bat` → 前端 `http://localhost:5173`

等前端窗口出现 `Local: http://localhost:5173`，浏览器打开这个地址即可。

几个 bat 都会在启动前先杀掉占用对应端口的旧进程，所以重复双击不会「端口被占用」。

### 方式 B：手动分别启动

四个终端，都在项目根目录执行：

```bash
# 1) 语音服务（可选）
powershell -NoProfile -ExecutionPolicy Bypass -File voice-service\start_furina_api.ps1

# 2) 后端（8000）
.venv\Scripts\python.exe -m uvicorn server.app:app --port 8000 --reload

# 3) 大模型监控台（8124，可选）
.venv\Scripts\python.exe server\llm_monitor.py --port 8124

# 4) 前端（5173）
npm run dev
```

后端加了 `--reload`，改 `server/` 下的 Python 会自动重启。

### 端口总表

| 端口 | 服务 | 地址 |
| --- | --- | --- |
| 5173 | 前端 Vite dev server | http://localhost:5173 |
| 8000 | 后端 FastAPI | http://127.0.0.1:8000 |
| 8124 | 大模型对话监控台 | http://127.0.0.1:8124 |
| 9880 | GPT-SoVITS 语音服务 | http://127.0.0.1:9880 |

前端所有 `/api/*` 请求都由 `vite.config.ts` 代理到 `8000`，所以浏览器里只访问 5173 就行。

### 登录账号（默认管理员）

第一次打开页面时用这个账号登录：

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | 管理员 |

- 后端首次启动时会自动创建它（`server/db.py` 的 `_ensure_admin()`），改过密码后不会被重置回去。
- 用管理员登录后，右上角能进**后台管理**：数据总览、模型库、发布公告、地图 Key。
- 普通用户也可以自己点「注册」新建账号，只是没有后台权限。
- **上线前记得把 `admin` 的密码改掉。**

---

## 六、配置

### 1. 大模型 Key（必须，否则 AI 对话不可用）

Key **不写在代码里**，而是按账号存在数据库：打开网页 → 注册/登录 → 右上角 **⚙ 设置 → 添加模型提供商**，填 Base URL（默认 `https://api.deepseek.com`）、模型名（默认 `deepseek-chat`）和你的 API Key。每个账号各自一份，加密存在 `user_providers` 表，加密用的主密钥是项目根目录的 `.keys/master.key`（首次运行自动生成，已加入 `.gitignore`，**不要删**，否则库里的 Key 全部解不开）。

没配 Key 时，聊天接口会返回「还没有可用的 API Key」，天气/行程/vlog 这类不需要模型的接口仍然可用。

### 2. 高德地图 Key（管理员在后台配，全局一份）

**不在代码里**，也不再由普通用户填。走这条路：用管理员账号登录 → 右上角进后台 → 顶部 tab **「地图 Key」** → 填 Key 和安全密钥 → 保存。所有登录用户通过 `GET /api/map` 读到同一份，前端刷新页面即生效，**改 Key 不用改代码、不用重启后端**。

怎么拿这个 Key：
1. 打开 [高德开放平台控制台](https://console.amap.com/dev/key/app) → 应用管理 → 我的应用 → 创建新应用（服务平台选 **Web端(JS API)**）。
2. 复制生成的 **Key**；如果列表里有 **安全密钥**（2021-12-02 之后申请的 Key 都有），一并复制，填到后台第二个框。
3. 在同一个应用的设置里配 **域名白名单**（本地调试可填 `localhost` / `127.0.0.1`），否则会报 `INVALID_USER_DOMAIN`。

几个坑：
- Key 类型必须是 **Web端(JS API)**。填成「Web服务」「Android」之类的会报 `USERKEY_PLAT_NOMATCH`（`infocode: 10009`）。
- 缺安全密钥会报 `INVALID_USER_SCODE`。
- 后台点「清空」后前端会提示「管理员还没在后台配置高德地图 Key」，行程面板不可用，但其它功能不受影响。

数据落在 `app_settings` 表（`key` / `value` 两列），对应接口：`GET /api/map`（登录用户读）、`GET|PUT|DELETE /api/admin/map`（管理员读写）。

### 3. 代码里的常量（`server/config.py`）

| 常量 | 作用 |
| --- | --- |
| `SOVITS_API_URL` | 语音服务地址，默认 `http://127.0.0.1:9880`，要和 `api_v2.py` 的端口一致 |
| `SOVITS_REF_AUDIO` | 参考音频，默认 `models/Furina_GPT_SoVITS/ref.wav`（3~10 秒干净人声） |
| `SOVITS_PROMPT_TEXT` | 参考音频对应的文字 |
| `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | 用户没填时的兜底默认值 |
| `CORS_ORIGINS` | 允许的前端来源（换了前端端口要同步改） |

### 4. 默认管理员

`admin` / `123456`，后端首次启动时自动创建（见 `server/db.py` 的 `_ensure_admin()`），详见 [「五、运行」的登录账号说明](#登录账号默认管理员)。

---

## 七、数据存在哪

| 内容 | 位置 | 说明 |
| --- | --- | --- |
| 用户 / 会话 / 对话 / 记忆 / 用量 | `server/app.db` | SQLite，删掉即重置（会重建表并补管理员） |
| 用户 API Key | `server/app.db` 的 `user_providers` 表 | Key 用 `server/keyvault.py` 加密，主密钥在项目根 `.keys/master.key` |
| 高德地图 Key | `server/app.db` 的 `app_settings` 表 | 管理员在后台「地图 Key」里改，全站共用一份 |
| 上传的音乐 | `server/tmp_music/<会话 token>/` | 临时文件：退出登录会清空，启动时也会清掉没有对应会话的目录 |
| 大模型请求日志 | `server/logs/llm_trace.jsonl` | 8124 监控台读这个文件，超过 8MB 自动轮转 |
| 内置背景音乐 | `public/Travelers' encore - Andrew Prahlow.mp3` | 播放器列表里那首「内置」，永久保留 |

清理规则：`sessions` 和 `usage_events` 都有 `expires_at` 列，过期行会在启动/登录时被删掉；`usage_events` 的 `user_id` 是 `NOT NULL`，未登录的请求不落库。

---

## 八、构建与检查

```bash
# 类型检查（会检查 .vue 里的 TS）
npm run type-check

# 生产构建（类型检查 + 打包到 dist/）
npm run build

# 只打包
npm run build-only

# 本地预览打包结果
npm run preview
```

> 如果 PowerShell 因为执行策略不允许跑 npm 脚本，可以直接调底层程序：
> ```bash
> node node_modules\vue-tsc\bin\vue-tsc.js --build
> node node_modules\vite\bin\vite.js build
> ```

打包时如果看到 `Some chunks are larger than 500 kB` 之类的警告，属正常（Live2D 和 pixi 体积大），不影响运行。

---

## 九、常见问题

**1. 页面能开，但聊天一直提示「还没有可用的 API Key」**
去设置里添加模型提供商；确认 Base URL 能连通、Key 没填错。

**2. 端口被占用 / 启动窗口一闪就关**
`run.bat` 已经把「杀旧进程」做进去了；如果还是失败，手动查占用：
```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen
```
再 `Stop-Process -Id <PID>`。

**3. 行程面板提示「管理员还没在后台配置高德地图 Key」**
用管理员账号进后台 → 「地图 Key」把 Key 和安全密钥填上并保存。若控制台报 `INVALID_USER_SCODE` 是缺安全密钥；报 `USERKEY_PLAT_NOMATCH` 是 Key 类型选错了（要用「Web端(JS API)」）；报 `INVALID_USER_DOMAIN` 是域名白名单没加。

**4. 天气面板数据来源显示 wttr.in / 只有 3 天**
后端有三条数据源：Open-Meteo → 挪威气象局 MET Norway → wttr.in。前两个不通时才退到 wttr.in（它只有 3 天）。排查本机到 `api.open-meteo.com`、`api.met.no` 的网络。

**5. 看 vlog 时提示「B站暂时拦住了这次搜索」**
B 站接口有频率限制（HTTP 412），等几十秒再点刷新即可。

**6. 打电话没有声音**
语音服务没起（9880）。检查 `_voice.bat` 窗口，或确认 `models/Furina_GPT_SoVITS/ref.wav` 存在。

**7. 语音服务报 CUDA / torch 相关错误**
先自检：`voice-service\.venv-gsv\Scripts\python.exe -c "import torch; print(torch.version.cuda, torch.cuda.is_available())"`。
打印 `None` 或 `False` 说明装成了 CPU 版（或驱动太旧）——重装带 CUDA 的 torch：
```bash
voice-service\.venv-gsv\Scripts\python.exe -m pip uninstall -y torch torchvision torchaudio
voice-service\.venv-gsv\Scripts\python.exe -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu134
```
如果报 `numpy` 相关的 `_ARRAY_API not found`，是把 numpy 升到 2.x 了，降回 `pip install "numpy<2.0"`。

**8. Live2D 模型不出来**
模型文件在 `public/芙宁娜（vts）/芙宁娜.model3.json`，需要 `live2dcubismcore.min.js`（同目录 `public/` 下）。浏览器控制台会打印具体缺哪个文件。

**9. 监控台 8124 打不开**
单独跑 `_monitor.bat` 看报错；它只依赖 Python 标准库和 `server/logs/` 目录。
