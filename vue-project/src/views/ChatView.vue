<!-- ====================================================================
  ChatView —— 登录后的主页面（三块结构，对应你画的框）
    蓝框 = 顶部导航条：左边标题、中间一排选项按钮、右边用户 + 退出
    黄框 = 左侧：Live2D 小人舞台
    红框 = 右侧：和 AI 聊天的界面（消息列表 + 输入框）
==================================================================== -->

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import MessageList from '../components/MessageList.vue'
import MessageInput from '../components/MessageInput.vue'
import Live2DStage from '../components/Live2DStage.vue'
import { useChatStream } from '../composables/useChatStream'

// ------------------------------------------------------------------
// Live2D 动作控制
// ------------------------------------------------------------------
const live2dRef = ref<InstanceType<typeof Live2DStage> | null>(null)
const showActions = ref(false)

// model3.json 里定义的 4 个动作组（Motions）
const motions = [
  { label: '待机', group: 'Idle',    index: 0 },
  { label: '摊手', group: 'TapBody', index: 0 },
  { label: '变芒', group: '变芒',    index: 0 },
  { label: '变荒', group: '变荒',    index: 0 },
]

// model3.json 里定义的 16 个表情（Expressions），也当作"动作"给芙芙换脸/换道具
const expressions = [
  '呆毛电风扇', '哭', '喝饮料', '大聪明',
  '小脸红', '帽子', '托脸', '拿勺子',
  '拿蛋糕', '捂嘴', '星星', '汗',
  '猫猫嘴', '生气', '走路切换', '鱼鱼',
]

function triggerMotion(group: string, index: number) {
  // 「待机」是自动循环的默认动画，直接 playMotion('Idle') 会被库拒绝，
  // 所以走专用的 resetToIdle：先停掉当前动作，再从头重播待机。
  if (group === 'Idle') {
    live2dRef.value?.resetToIdle()
  } else {
    live2dRef.value?.playMotion(group, index)
  }
}

function triggerExpression(name: string) {
  live2dRef.value?.setExpression(name)
}

function toggleActions() {
  showActions.value = !showActions.value
}

const props = defineProps({
  username: { type: String, default: '' },
})
const emit = defineEmits(['logout'])

// 聊天逻辑全部在 useChatStream 里（发消息、假流式回复、消息列表）
// 界面组件只负责展示，互相之间靠 props 和事件传话
const { messages, isTyping, isThinking, sendMessage } = useChatStream()

// ------------------------------------------------------------------
// 顶部导航按钮（参考你发的那张蓝色导航条，图片和文字先留空）
//   想加第 6 个按钮就在数组里再加一个 { icon: '', text: '' }
//   想填内容时：icon 填图片路径（如 '/xxx.png'），text 填文字（如 '行程规划'）
// ------------------------------------------------------------------
const navButtons = ref([
  { icon: '', text: '' },
  { icon: '', text: '' },
  { icon: '', text: '' },
  { icon: '', text: '' },
  { icon: '', text: '' },
])

// 当前选中的是第几个按钮（点击就高亮，切换逻辑以后再填）
const activeNav = ref(0)

function selectNav(index: number) {
  activeNav.value = index
  // TODO: 以后在这里根据 index 切换功能面板（比如打开行程规划页）
}

// ------------------------------------------------------------------
// 音量控制
//   现在控制的是背景音乐（public 下的 "Travelers' encore - Andrew Prahlow.mp3"）。
//   以后接了语音合成（TTS），把语音那个 <audio> 也接到 applyVolume 里就行：
//     ① 控制 TTS 播放的 <audio>：ttsAudio.volume = volume.value / 100
//     ② 或每帧 setMouthOpen 时，同步给 Web Audio 的 gainNode.gain.value（声音总闸 + 口型）
// ------------------------------------------------------------------
const BGM_SRC = "/Travelers' encore - Andrew Prahlow.mp3"

const volume = ref(50)      // 0~100，默认 80
const muted = ref(false)    // 静音开关
const audioRef = ref<HTMLAudioElement | null>(null)

// 把音量写进 <audio>：静音时直接给 0，恢复时按滑块数值还原
function applyVolume() {
  const el = audioRef.value
  if (!el) return
  el.volume = muted.value ? 0 : Math.min(1, Math.max(0, volume.value / 100))
}

// 滑块拖动 / 静音切换都会触发
watch([volume, muted], applyVolume)

function toggleMute() {
  muted.value = !muted.value
}

// 浏览器默认拦截"带声音的自动播放"，被拦时等用户第一次点击页面再试一次
function tryPlay() {
  audioRef.value?.play().catch(() => {})
}
function resumeOnFirstGesture() {
  tryPlay()
  document.removeEventListener('pointerdown', resumeOnFirstGesture)
}

onMounted(() => {
  applyVolume()
  tryPlay()
  document.addEventListener('pointerdown', resumeOnFirstGesture)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', resumeOnFirstGesture)
})
</script>

<template>
  <div class="chat-page">
    <!-- 背景音乐：没有界面，只被上面的音量键控制。不想放歌就把这行删掉 -->
    <audio ref="audioRef" :src="BGM_SRC" loop preload="auto" autoplay />
    <!-- ============ 蓝框：顶部导航条 ============ -->
    <header class="chat-header">
      <div class="chat-brand">
        <span class="chat-title">旅行助手</span>
      </div>

      <!--
        选项按钮：margin-left 把整组按钮往左拉（数值越大越靠右，
        想再左一点就把 40px 改小或删掉，想居中就改成 margin: 0 auto）
      -->
      <nav class="chat-nav">
        <button
          v-for="(btn, i) in navButtons"
          :key="i"
          class="nav-btn"
          :class="{ 'nav-btn--active': i === activeNav }"
          @click="selectNav(i)"
        >
          <!-- 图标槽：btn.icon 有值才会渲染 <img>，现在留空不显示 -->
          <img v-if="btn.icon" class="nav-btn__icon" :src="btn.icon" alt="" />
          <!-- 文字槽：现在都是空字符串，填上就显示 -->
          <span v-if="btn.text" class="nav-btn__text">{{ btn.text }}</span>
        </button>
      </nav>

      <div class="chat-user-box">
        <span class="chat-user">{{ props.username }}</span>

        <!-- 音量键：小喇叭（点击静音 / 恢复）+ 滑块（0~100） -->
        <div class="volume-box">
          <button
            class="volume-btn"
            :class="{ 'volume-btn--muted': muted }"
            :title="muted ? '取消静音' : '静音'"
            @click="toggleMute"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M4 9.5h3.2L11.5 6v12l-4.3-3.5H4z" fill="currentColor" />
              <template v-if="muted">
                <path
                  d="M15.5 9.5l5 5M20.5 9.5l-5 5"
                  stroke="currentColor"
                  stroke-width="1.8"
                  fill="none"
                  stroke-linecap="round"
                />
              </template>
              <template v-else>
                <path
                  d="M15 9.2a4.5 4.5 0 0 1 0 5.6"
                  stroke="currentColor"
                  stroke-width="1.7"
                  fill="none"
                  stroke-linecap="round"
                />
                <path
                  d="M17.8 6.8a8 8 0 0 1 0 10.4"
                  stroke="currentColor"
                  stroke-width="1.7"
                  fill="none"
                  stroke-linecap="round"
                />
              </template>
            </svg>
          </button>

          <input
            v-model.number="volume"
            class="volume-slider"
            type="range"
            min="0"
            max="100"
            :title="muted ? '已静音' : `音量 ${volume}%`"
          />
        </div>

        <button class="chat-logout" @click="emit('logout')">退出</button>
      </div>
    </header>

    <!-- ============ 黄框 + 红框：主体两栏 ============ -->
    <main class="chat-main">
      <!-- 黄框：Live2D 小人
           依赖已装好（pixi.js@6 + pixi-live2d-display@0.4.0），Cubism Core 在 index.html 里引入。
           模型在 public/芙宁娜（vts）/ 下（原文件已备份为 芙宁娜.model3.json.bak）。
           已在 model3.json 里补了 Motions（Idle / TapBody / 变芒 / 变荒）和 16 个 Expressions，
           并给 EyeBlink 组填上 ParamEyeLOpen / ParamEyeROpen，所以现在会自动待机动画 + 眨眼。
           通过 ref 调用：playMotion('变芒')、setExpression('哭')、setMouthOpen(0~1)。 -->
      <section class="chat-stage">
        <Live2DStage ref="live2dRef" model-url="/芙宁娜（vts）/芙宁娜.model3.json" />

        <!-- ====== Live2D 动作控制面板（左下角） ====== -->
        <div class="live2d-actions" :class="{ 'live2d-actions--open': showActions }">
          <!-- 小圆按钮：点开/收起 -->
          <button class="live2d-actions__toggle" @click="toggleActions" title="控制芙芙">
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <circle cx="12" cy="6" r="1.6" fill="currentColor" />
              <circle cx="12" cy="12" r="1.6" fill="currentColor" />
              <circle cx="12" cy="18" r="1.6" fill="currentColor" />
            </svg>
          </button>

          <!-- 弹出面板：动作 + 表情按钮列表 -->
          <div class="live2d-actions__panel">
            <!-- 动作分组 -->
            <span class="live2d-actions__label">动作</span>
            <button
              v-for="m in motions"
              :key="m.group"
              class="live2d-actions__btn"
              @click="triggerMotion(m.group, m.index)"
            >
              {{ m.label }}
            </button>

            <!-- 分隔线 -->
            <div class="live2d-actions__divider"></div>

            <!-- 表情分组（2 列网格，16 个表情） -->
            <span class="live2d-actions__label">表情</span>
            <div class="live2d-actions__grid">
              <button
                v-for="name in expressions"
                :key="name"
                class="live2d-actions__btn"
                @click="triggerExpression(name)"
              >
                {{ name }}
              </button>
            </div>

            <!-- 分隔线 -->
            <div class="live2d-actions__divider"></div>

            <!-- AI 控制按钮（占位，以后再接入） -->
            <button class="live2d-actions__btn live2d-actions__btn--ai" disabled title="AI 自动操控（即将上线）">
              <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                <path
                  d="M12 2a2.5 2.5 0 0 0-2.5 2.5v.5H7a3 3 0 0 0-3 3v9a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V8a3 3 0 0 0-3-3h-2.5v-.5A2.5 2.5 0 0 0 12 2z"
                  fill="currentColor" opacity="0.35" />
                <circle cx="8.5" cy="11" r="2" fill="currentColor" />
                <circle cx="15.5" cy="11" r="1.8" fill="currentColor" />
                <path
                  d="M8.5 15.5c1.2 1.8 3.7 2.2 5.5.8"
                  stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" />
              </svg>
              AI 控制
            </button>
          </div>
        </div>
      </section>
      

      <!-- 红框：聊天面板 = 消息列表 + 输入框，上下拼起来 -->
      <section class="chat-panel">
        <MessageList :messages="messages" :is-typing="isTyping" :is-thinking="isThinking" />
        <MessageInput :disabled="isTyping" @send="sendMessage" />
      </section>
    </main>
  </div>
</template>

<style scoped>
/* ============ 整页布局 ============ */
.chat-page {
  height: 100vh;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;   /* 导航条在上，主体在下 */
  gap: 18px;
  padding: 18px 22px;
}

/* ============ 蓝框：顶部导航条 ============ */
.chat-header {
  flex: 0 0 auto;
  height: 56px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  padding: 0 18px;
  border-radius: 14px;
  background: #3d7fd6;              /* 参考图那个蓝 */
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12);
  color: #fff;
}

.chat-title {
  font-size: 1.15rem;
  font-weight: 500;
  white-space: nowrap;
}

/* ---- 中间那排选项按钮 ---- */
.chat-nav {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: 48px;   /* ★ 整组按钮偏左的位置就在这调 */
  flex: 0 1 auto;
  overflow-x: auto;    /* 按钮太多时横向滚动，不挤爆导航条 */
}

/* 按钮本体：胶囊形，默认透明底白字，选中变白底蓝字（参考图效果） */
.nav-btn {
  flex: 0 0 auto;
  min-width: 76px;             /* 空按钮也保持宽度，不会缩没 */
  height: 32px;
  padding: 0 16px;
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: none;
  border-radius: 16px;
  background: transparent;
  color: rgba(255, 255, 255, 0.92);
  font-size: 0.92rem;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}
.nav-btn:hover { background: rgba(255, 255, 255, 0.16); }

/* 选中的按钮：白底蓝字 */
.nav-btn--active {
  background: #fffdf8;
  color: #3d7fd6;
  font-weight: 500;
}

/* 图标 / 文字两个槽位 */
.nav-btn__icon { width: 18px; height: 18px; object-fit: contain; }
.nav-btn__text { white-space: nowrap; }

/* ---- 右侧用户区 ---- */
.chat-user-box {
  margin-left: auto;       /* 推到最右边 */
  display: flex;
  align-items: center;
  gap: 12px;
}
.chat-user { font-size: 0.95rem; opacity: 0.95; }

/* ---- 音量键：小喇叭 + 细滑块 ---- */
.volume-box {
  display: flex;
  align-items: center;
  gap: 4px;
}

.volume-btn {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: #fff;
  cursor: pointer;
  transition: background 0.2s, opacity 0.2s;
}
.volume-btn:hover { background: rgba(255, 255, 255, 0.16); }
.volume-btn--muted { opacity: 0.6; }

/* accent-color 一行就能把滑块染成米白色，不用手写伪元素 */
.volume-slider {
  width: 90px;
  accent-color: #fffdf8;
  cursor: pointer;
}

.chat-logout {
  height: 30px;
  padding: 0 14px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: 15px;
  background: transparent;
  color: #fff;
  font-size: 0.88rem;
  cursor: pointer;
  transition: background 0.2s;
}
.chat-logout:hover { background: rgba(255, 255, 255, 0.16); }

/* ============ 主体两栏 ============ */
.chat-main {
  flex: 1;                 /* 吃掉导航条以下的全部高度 */
  min-height: 0;           /* 关键：允许子元素收缩，聊天列表才能正常滚动 */
  display: flex;
  gap: 22px;
}

/* ---- 黄框：Live2D ---- */
/* flex 用 1.3 : 1 的比例，左边大约占 56%，和你的图接近 */
.chat-stage {
  flex: 1.3;
  min-width: 0;
  position: relative;        /* 动作控制面板相对它定位 */
  border: 2px solid rgba(255, 253, 248, 0.55);
  border-radius: 18px;
  overflow: hidden;          /* 圆角裁边 + 面板不溢出 */
}

/* ====== Live2D 动作控制面板 ====== */
.live2d-actions {
  position: absolute;
  left: 14px;
  bottom: 14px;
  z-index: 10;
  display: flex;
  flex-direction: column-reverse;  /* 按钮在面板下面，向上弹出 */
  align-items: flex-start;
  gap: 10px;
}

/* 小圆按钮（三条横线 = 菜单图标） */
.live2d-actions__toggle {
  width: 36px;
  height: 36px;
  border: 1.5px solid rgba(255, 253, 248, 0.7);
  border-radius: 50%;
  background: rgba(47, 62, 70, 0.55);
  backdrop-filter: blur(6px);
  color: #fffdf8;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.2s, transform 0.2s;
  flex: 0 0 auto;
}
.live2d-actions__toggle:hover {
  background: rgba(47, 62, 70, 0.78);
  transform: scale(1.08);
}

/* 打开时小按钮转 90° */
.live2d-actions--open .live2d-actions__toggle {
  transform: rotate(90deg);
}

/* 弹出面板：默认隐藏，打开时从按钮上方滑出 */
.live2d-actions__panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  border-radius: 14px;
  background: rgba(47, 62, 70, 0.66);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 253, 248, 0.35);
  max-height: min(68vh, 520px);   /* 按钮太多时面板内部滚动，不顶出舞台 */
  overflow-y: auto;
  opacity: 0;
  transform: translateY(8px);
  pointer-events: none;
  transition: opacity 0.22s, transform 0.22s;
}

/* 面板滚动条：细一点，和毛玻璃风格搭 */
.live2d-actions__panel::-webkit-scrollbar { width: 6px; }
.live2d-actions__panel::-webkit-scrollbar-thumb {
  background: rgba(255, 253, 248, 0.3);
  border-radius: 3px;
}

/* 分组小标题：动作 / 表情 */
.live2d-actions__label {
  padding: 2px 6px 0;
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  color: rgba(255, 253, 248, 0.55);
}

/* 表情网格：2 列排布 */
.live2d-actions__grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
}
.live2d-actions--open .live2d-actions__panel {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

/* 动作按钮 */
.live2d-actions__btn {
  min-width: 72px;
  height: 32px;
  padding: 0 14px;
  border: 1px solid rgba(255, 253, 248, 0.45);
  border-radius: 16px;
  background: transparent;
  color: #fffdf8;
  font-size: 0.88rem;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.18s, border-color 0.18s;
}
.live2d-actions__btn:hover {
  background: rgba(255, 253, 248, 0.18);
  border-color: rgba(255, 253, 248, 0.75);
}

/* 分隔线 */
.live2d-actions__divider {
  height: 1px;
  margin: 2px 2px;
  background: rgba(255, 253, 248, 0.25);
}

/* AI 控制按钮（占位，disabled） */
.live2d-actions__btn--ai {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  opacity: 0.5;
  cursor: not-allowed;
  border-style: dashed;
}
.live2d-actions__btn--ai:hover {
  background: transparent;
  border-color: rgba(255, 253, 248, 0.45);
}

/* ---- 红框：聊天面板 ---- */
.chat-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;  /* 上：消息列表（可滚），下：输入框（固定） */
  border: 2px solid rgba(255, 253, 248, 0.55);
  border-radius: 18px;
  background: rgba(20, 60, 60, 0.30);  /* 半透明深底，字看得清又不挡海 */
  backdrop-filter: blur(2px);
  overflow: hidden;        /* 圆角内的滚动条裁齐 */
}

/* ---- 窄屏：上下堆叠 ---- */
@media (max-width: 900px) {
  .chat-main { flex-direction: column; }
  .chat-stage { flex: 1; min-height: 300px; }
  .chat-nav { margin-left: 20px; }
}
</style>
