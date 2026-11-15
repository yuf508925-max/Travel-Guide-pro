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
│  ├─ check_assets.py       # 检查语音资源是否齐全（缺什么一目了然）
│  ├─ fetch_assets.py       # 一键下载公开的语音资源（底模 / G2PW / ffmpeg）
│  └─ start_furina_api.ps1  # 启动语音服务（路径自适应，可放任意目录）
├─ models/Furina_GPT_SoVITS/# 芙宁娜音色权重与 ref.wav（需单独获取，见 4.4）
└─ dist/                    # 前端打包产物（npm run build 生成）
```

---

## 三、环境要求

| 需要安装 | 版本 | 说明 |
| --- | --- | --- |
| Node.js | `^22.18.0` 或 `>=24.12.0` | 前端；低于这个版本 Vite 8 起不来 |
| Python | 3.10+（后端在 3.13 上验证） | 后端 `server/` |
| NVIDIA 显卡 + 驱动（可选） | CUDA 13.4（本项目实测环境） | 只有语音服务用；没有也能跑，只是没声音 |
| 磁盘空间（可选） | 语音资源约 2 GB | 不装语音服务则不需要 |

---

## 四、安装依赖

源码、前端资源（Live2D 模型、背景、内置音乐）都已经在仓库里，**不需要另外下载**。

但**语音服务用到的模型和 ffmpeg（约 1.75 GB）不在仓库里**（单文件超过 GitHub 的 100 MB 上限，已被 `.gitignore` 排除），必须按 4.4 单独补装。以下命令都在项目根目录 `vue-project/` 执行。

### 1. 前端

```bash
npm install
```

### 2. 后端

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r server/requirements.txt
```

`server/requirements.txt`：`fastapi`、`uvicorn[standard]`、`openai`、`truststore`、`cryptography`（用户 API Key 的加密依赖，缺了后端起不来）。

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

### 4. 语音资源（不在仓库里，必须单独补装）

GitHub 对单个文件有 **100 MB** 的硬上限，下面这些都被 `.gitignore` 排除了（`/models/`、`*.pth`、`*.ckpt`、`*.onnx`、`voice-service/GPT_SoVITS/pretrained_models/`、`voice-service/GPT_SoVITS/text/G2PWModel/`、`voice-service/ffmpeg-bin/`），所以 `git clone` 下来**没有**它们。不补装，语音服务一定起不来（聊天、天气、行程、vlog 不受影响）。

> 需要说明的是：旧版 `.gitignore` 写的是 `models/`（没有前导 `/`），这条规则会匹配**任意层级**叫 `models` 的目录，结果把源码目录 `voice-service/GPT_SoVITS/AR/models/`、`voice-service/tools/AP_BWE_main/models/` 也一起忽略了，克隆下来直接报 `ModuleNotFoundError: No module named 'AR.models'`。现在已改成 `/models/`，只忽略仓库根目录下的音色权重，缺的源码也已补进仓库。

| 资源 | 放到哪 | 体积 | 来源 |
| --- | --- | --- | --- |
| GPT-SoVITS 底模（hubert / roberta / sv） | `voice-service/GPT_SoVITS/pretrained_models/` | 约 0.95 GB | HuggingFace 镜像 `lj1995/GPT-SoVITS` |
| G2PW 多音字模型 | `voice-service/GPT_SoVITS/text/G2PWModel/` | 约 0.6 GB | ModelScope（缺失时首次合成也会自动下载） |
| ffmpeg / ffprobe | `voice-service/ffmpeg-bin/` | 约 0.2 GB | gyan.dev |
| **芙宁娜音色权重** + 参考音频 | `models/Furina_GPT_SoVITS/` | 约 0.3 GB | **只在作者手里**，见第 2 步 |
| （可选）v2 官方底模 | `.../pretrained_models/gsv-v2final-pretrained/` | 约 0.35 GB | 只有想切回官方 v2 音色才需要 |

#### 第 1 步：一键下载公开资源（推荐）

```bash
python voice-service\fetch_assets.py
```

脚本从 hf-mirror.com / ModelScope / gyan.dev 下载上表前三项（约 1.75 GB），支持断点续传，已存在的文件自动跳过。想先看会下什么：`python voice-service\fetch_assets.py --dry-run`。

#### 第 2 步：放芙宁娜音色权重（必须手动）

把下面 3 个文件放到 `models\Furina_GPT_SoVITS\`：

```
models\Furina_GPT_SoVITS\
├─ Funina-e15.ckpt      GPT 模型（约 148 MB）
├─ Funina_e8_s464.pth   SoVITS 模型（约 165 MB）
└─ ref.wav              3~10 秒参考音频
```

这三个文件没有公开下载地址，只能：

1. 从作者原来那台能跑语音的电脑上，把整个 `models/Furina_GPT_SoVITS/` 目录拷过来；
2. 去 [Releases](https://github.com/yuf508925-max/Travel-Guide-pro/releases) 看作者有没有上传（作者上传方法见第十节）；
3. 找作者要网盘链接。

> 没有它们语音服务能启动，但合成不出芙宁娜的声音。可以临时改用 GPT-SoVITS 官方底模 + 任意 3~10 秒参考音频，只是音色不是芙宁娜。

#### 第 3 步：检查

```bash
python voice-service\check_assets.py
```

全部显示 `ok` 再启动语音服务；缺什么、该放哪，它会直接列出来。

> **不想用脚本？** 手动命令：`python -m pip install -U huggingface_hub`，然后
> `set HF_ENDPOINT=https://hf-mirror.com`（PowerShell 用 `$env:HF_ENDPOINT="https://hf-mirror.com"`），
> 再执行
> `huggingface-cli download lj1995/GPT-SoVITS --include "chinese-hubert-base/*" "chinese-roberta-wwm-ext-large/*" "sv/*" --local-dir voice-service\GPT_SoVITS\pretrained_models`
> （新版 huggingface_hub 里命令叫 `hf download`，参数相同）。
> G2PW 手动下载 <https://www.modelscope.cn/models/kamiorinn/g2pw/resolve/master/G2PWModel_1.1.zip>，解压后把 `G2PWModel` 目录放到 `voice-service\GPT_SoVITS\text\G2PWModel`（确认里面有 `g2pW.onnx`）。
> ffmpeg 手动下载 <https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip>，把 `bin\ffmpeg.exe`、`bin\ffprobe.exe` 解压到 `voice-service\ffmpeg-bin\`。

---

## 五、运行

> 只想先看界面：装完 4.1（前端）和 4.2（后端），然后跑「后端 + 前端」两个窗口就够了。语音服务是可选的，补完 4.4 再启动。

### 方式 A：一键启动（推荐）

双击项目根目录的 **`run.bat`**，会依次弹出四个窗口：

1. `_voice.bat` → GPT-SoVITS 语音服务 `http://127.0.0.1:9880`（没装语音环境/没补 4.4 的资源时这个窗口会报错退出，关掉即可）
2. `_api.bat` → 后端 `http://127.0.0.1:8000`
3. `_monitor.bat` → 大模型监控台 `http://127.0.0.1:8124`
4. `_web.bat` → 前端 `http://localhost:5173`

等前端窗口出现 `Local: http://localhost:5173`，浏览器打开这个地址即可。语音服务第一次启动要加载模型，等 `http://127.0.0.1:9880` 有响应大约需要 30~90 秒。

几个 bat 都会在启动前先杀掉占用对应端口的旧进程，所以重复双击不会「端口被占用」。

### 方式 B：手动分别启动

四个终端，都在项目根目录执行：

```bash
# 1) 语音服务（可选，先补完 4.4 的资源）
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
语音服务没起（9880）。检查 `_voice.bat` 窗口，或确认 `models/Furina_GPT_SoVITS/ref.wav` 存在。资源是否齐全直接跑：
```bash
python voice-service\check_assets.py
```

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

**10. 后端启动报 `ModuleNotFoundError: No module named 'cryptography'`**
旧版 `requirements.txt` 漏了这个依赖，已补上。重新装一次：
```bash
.venv\Scripts\python.exe -m pip install -r server/requirements.txt
```

**11. 语音服务窗口一闪就关，日志里有 `FileNotFoundError`（`Funina-e15.ckpt` / `g2pW.onnx` / `ffmpeg.exe` / `pytorch_model.bin`），或 `No such file or directory: 'ffmpeg'`**
语音资源没补全。按第四节 4 补装，然后运行：
```bash
python voice-service\check_assets.py
```

**12. 换了台电脑 / 换了目录后，语音服务报 `D:\test\...` 路径不存在**
旧版的 `start_furina_api.ps1` 和 `furina_infer.yaml` 写死了作者本机的绝对路径，现已改成相对路径；确保你拉到的是最新代码。

**13. `git clone` 下来发现 `voice-service` 里少了很多文件**
分两种情况：

- **大文件**（`pretrained_models/`、`G2PWModel/`、`ffmpeg-bin/`、根目录 `models/`）：正常，被 `.gitignore` 排除、GitHub 也不收超过 100 MB 的单文件，按第四节 4 补装即可。
- **源码文件**（`GPT_SoVITS/AR/models/*.py`、`GPT_SoVITS/configs/*.yaml`）：旧版 `.gitignore` 的 `models/` 规则误伤了它们，表现为启动报 `ModuleNotFoundError: No module named 'AR.models'` 或 `FileNotFoundError: tts_infer.yaml`。已修正为 `/models/` 并把文件补进仓库，拉最新代码即可。

**14. `pip install -r server\requirements.txt` 报 `UnicodeDecodeError: 'gbk' codec can't decode byte ...`**
Windows 中文环境下 pip 会用 GBK 解码 requirements 文件，文件里如果有 UTF-8 的中文注释就会炸。仓库里这个文件现在已经改成纯 ASCII 注释；如果你自己往里加注释，请用英文，或者另存为「UTF-8 带 BOM」。

---

## 十、给仓库作者：大文件怎么传上 GitHub

`git push` 传不上去不是网络问题，是 GitHub 的限制：

- **单文件 > 100 MB** 直接拒收，报错形如 `remote: error: File models/... is 148.00 MB; this exceeds GitHub's file size limit of 100.00 MB`；
- 仓库超过 1 GB 会收到体积警告；
- `.gitignore` 里 `/models/`、`*.pth`、`*.ckpt`、`*.onnx`、`voice-service/GPT_SoVITS/pretrained_models/`、`voice-service/ffmpeg-bin/` 等规则本来就把它们排除了，所以现在 GitHub 上没有这些文件。

> ⚠️ 忽略目录的规则记得加前导 `/`：`models/` 会忽略所有同名子目录，`/models/` 才只忽略仓库根目录那一个（见第四节 4 的说明）。同理，`voice-service/GPT_SoVITS/configs/.gitignore` 原来写的 `*.yaml` 会把 `tts_infer.yaml`、`s1*.yaml` 一起排掉，现在只忽略 `*.tmp` / `*.bak`。

推荐用 **GitHub Releases**（单个附件上限 2 GB，不占仓库体积）。装好 GitHub CLI 并登录（`winget install GitHub.cli`，然后 `gh auth login`），在项目根目录执行：

```powershell
gh release create voice-assets-v1 `
  "models/Furina_GPT_SoVITS/Funina-e15.ckpt" `
  "models/Furina_GPT_SoVITS/Funina_e8_s464.pth" `
  "models/Furina_GPT_SoVITS/ref.wav" `
  --title "芙宁娜语音资源 v1" `
  --notes "下载后放到 models/Furina_GPT_SoVITS/ 目录下即可"
```

传完把 Release 链接填到第四节 4 的第 2 步。

其它约 1.75 GB 的公开资源（底模 / G2PW / ffmpeg）**不用传**，`fetch_assets.py` 已经能从公开镜像下载。

不要试图 `git add -f` 把权重塞进仓库：>100 MB 会被拒；用 Git LFS 免费额度只有 1 GB，而且克隆的人还得额外装 LFS。也不要提交 `.venv/`、`.venv-gsv/`、`node_modules/`、`server/app.db`、`.keys/`。
