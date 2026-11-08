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
import WeatherPanel from '../components/WeatherPanel.vue'
import BalanceWidget from '../components/BalanceWidget.vue'
import RoutePlanner from '../components/RoutePlanner.vue'
import { resetAmapConfig } from '../composables/useAmap'
import VolumeMenu from '../components/VolumeMenu.vue'
import SettingsMenu from '../components/SettingsMenu.vue'
import PhoneCall from '../components/PhoneCall.vue'
import CallPanel from '../components/CallPanel.vue'
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
const { messages, isTyping, isThinking, sendMessage, holdAi, takeHeld } = useChatStream()

// ------------------------------------------------------------------
// 顶部导航按钮（红框里那三个）
//   现在只做"按钮本体 + 选中高亮"，点一下切换高亮，功能都还没接。
//   以后接功能：在 selectNav() 里根据 key 打开对应面板即可。
//   想加第 4 个按钮，就在数组里再加一项（key 要唯一）。
// ------------------------------------------------------------------
const navButtons = ref([
  {
    key: 'weather',
    text: '天气',
    hint: '天气查询',
    // 太阳：一个圆 + 八条光线（图标直接用 path 画，不依赖图片，选中时跟着变蓝）
    paths: [
      'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8',
      'M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
    ],
  },
  {
    key: 'trip',
    text: '行程',
    hint: '行程规划 · 高德路线地图',
    // 定位针：外轮廓 + 中间的小孔
    paths: [
      'M12 21s7-6.3 7-11.2A7 7 0 0 0 5 9.8C5 14.7 12 21 12 21Z',
      'M12 12a2.4 2.4 0 1 0 0-4.8 2.4 2.4 0 0 0 0 4.8',
    ],
  },
  {
    key: 'poster',
    text: '旅行一图流',
    hint: '旅行一图流 · 即将上线',
    // 图片框：外框 + 左上小太阳 + 底部的山，用来表示"把行程画成一张图"
    paths: [
      'M5 3.5h14a1.5 1.5 0 0 1 1.5 1.5v14a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19V5A1.5 1.5 0 0 1 5 3.5Z',
      'M9.2 9.5a1.25 1.25 0 1 0 0-2.5 1.25 1.25 0 0 0 0 2.5',
      'M4.2 17.4l4.6-4.9 3.1 3.1 2.5-2.5 5.4 5.3',
    ],
  },
  {
    key: 'tts',
    text: '和芙芙打电话',
    hint: '语音通话',
    // 电话听筒：一条闭环的听筒轮廓（比起话筒更贴合"打电话"这个动作）
    paths: [
      'M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.9.6 2.8.7a2 2 0 0 1 1.7 2Z',
    ],
  },
])

// 当前选中的是第几个按钮（点击就高亮，切换逻辑以后再填）
const activeNav = ref(0)

// ------------------------------------------------------------------
// 天气小窗口
//   showWeather 控制弹窗开不开；上次查过的城市存 localStorage，
//   下次打开还是这个城市（隐私模式下 localStorage 会抛异常，所以都包 try）。
// ------------------------------------------------------------------
const showWeather = ref(false)
// 行程面板（高德路线地图）
const showRoute = ref(false)
// 上次查过的省 / 市，分开存；下次打开直接回到那个城市
const weatherProvince = ref(readSavedPlace().province)
const weatherCity = ref(readSavedPlace().city)

function readSavedPlace(): { province: string; city: string } {
  try {
    return {
      province: localStorage.getItem('weather-province') || '山东',
      city: localStorage.getItem('weather-city') || '青岛',
    }
  } catch {
    return { province: '山东', city: '青岛' }
  }
}

function saveWeatherPlace(province: string, city: string) {
  weatherCity.value = city
  weatherProvince.value = province
  try {
    localStorage.setItem('weather-province', province)
    localStorage.setItem('weather-city', city)
  } catch {
    // 存不进去不影响这次查询
  }
}

function closeWeather() {
  showWeather.value = false
}

// ------------------------------------------------------------------
// 右上角的小弹窗：音量 / 设置
//   同一时刻只允许开一个（开设置就收起音量，反之亦然），
//   打开天气弹窗时也会把这两个收起来。
// ------------------------------------------------------------------
const openMenu = ref<'volume' | 'settings' | null>(null)

function toggleMenu(name: 'volume' | 'settings') {
  openMenu.value = openMenu.value === name ? null : name
  if (openMenu.value) showWeather.value = false
}



const showCall = ref(false)
// 通话模式：正文已收齐但语音还在合成，这期间继续显示思考提示
const callPending = ref(false)
// idle = 没在打；prompt = 已弹出"拨出"图标，等你点；active = 通话中
const callStage = ref<'idle' | 'prompt' | 'active'>('idle')
const phoneRef = ref<InstanceType<typeof PhoneCall> | null>(null)

function dialCall() {
  callStage.value = 'active'
  showCall.value = true
}

function closeCall() {
  showCall.value = false
  callStage.value = 'idle'
}

function selectNav(index: number) {
  const key = navButtons.value[index]?.key
  openMenu.value = null

  // 电话：先弹出一个"拨出"图标，点那个图标才真正拨号
  if (key === 'tts') {
    showWeather.value = false
    showRoute.value = false
    if (callStage.value === 'idle') {
      callStage.value = 'prompt'
    } else if (callStage.value === 'prompt') {
      callStage.value = 'idle'
    } else {
      phoneRef.value?.toggleMinimize()
    }
    activeNav.value = index
    return
  }

  // 天气：点一下开/关那个小窗口
  if (key === 'weather') {
    showRoute.value = false
    showWeather.value = !showWeather.value
    activeNav.value = index
    return
  }

  // 行程：打开路线规划面板（高德地图）
  if (key === 'trip') {
    showWeather.value = false
    showRoute.value = !showRoute.value
    activeNav.value = index
    return
  }

  // 其它按钮：先只切高亮，并把天气窗口收起来
  showWeather.value = false
  showRoute.value = false
  activeNav.value = index
  // TODO: 以后在这里根据 key 打开对应面板：
  //   trip → 行程规划   poster → 旅行一图流   tts → 语音通话
}

// ------------------------------------------------------------------
// 音量控制
//   现在控制的是背景音乐（public 下的 "Travelers' encore - Andrew Prahlow.mp3"）。
//   以后接了语音合成（TTS），把语音那个 <audio> 也接到 applyVolume 里就行：
//     ① 控制 TTS 播放的 <audio>：ttsAudio.volume = volume.value / 100
//     ② 或每帧 setMouthOpen 时，同步给 Web Audio 的 gainNode.gain.value（声音总闸 + 口型）
// ------------------------------------------------------------------
const BGM_SRC = "/Travelers' encore - Andrew Prahlow.mp3"

const bgmVolume = ref(50)    // 背景音乐 0~100
const voiceVolume = ref(80)  // 芙芙说话 0~100（电话窗口用）
const muted = ref(false)     // 背景音乐静音开关，和语音无关
const voiceMuted = ref(false) // 语音静音开关（电话里的芙芙）
const audioRef = ref<HTMLAudioElement | null>(null)

// 把音量写进 <audio>：静音时直接给 0，恢复时按滑块数值还原
function applyVolume() {
  const el = audioRef.value
  if (!el) return
  el.volume = muted.value ? 0 : Math.min(1, Math.max(0, bgmVolume.value / 100))
}

// 滑块拖动 / 静音切换都会触发
watch([bgmVolume, muted], applyVolume)

// ------------------------------------------------------------------
// 通话模式：文字先攒着，等语音合成好再"边说话边跳字"
//   holdAi = true 时，useChatStream 不往气泡里写字，而是把整段攒起来；
//   一轮结束后交给电话窗口一次性合成（一口气说完），
//   拿到音频时长后按同样节奏把文字放出来。
// ------------------------------------------------------------------
watch(showCall, (open) => {
  holdAi.value = open
  if (!open) callPending.value = false
  // 通话中途关掉：把攒下来的文字直接显示，别丢内容
  if (!open) {
    const held = takeHeld()
    if (held) held.message.text = held.text
  }
})

function revealText(message: { text: string }, full: string, durationMs: number) {
  const span = Math.max(900, durationMs || full.length * 180)
  const start = performance.now()
  const step = () => {
    const ratio = Math.min(1, (performance.now() - start) / span)
    message.text = full.slice(0, Math.floor(full.length * ratio))
    if (ratio < 1) requestAnimationFrame(step)
    else message.text = full
  }
  requestAnimationFrame(step)
}

watch(isTyping, async (typing) => {
  if (typing) {
    // 通话中：正文还在生成，继续显示思考提示
    if (showCall.value) callPending.value = true
    return
  }
  if (!showCall.value) return
  const held = takeHeld()
  if (!held) return

  const { message, text } = held
  message.text = ''
  const duration = (await phoneRef.value?.speakAll(text)) ?? 0
  // 语音已经开口，撤掉思考提示，文字跟着音频节奏跳出来
  callPending.value = false
  revealText(message, text, duration)
})


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
  // 退出登录时清掉当前账号的高德配置缓存，换账号会重新从后端读
  resetAmapConfig()
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
        红框里的功能按钮：天气 / 行程 / 旅行一图流 / 和芙芙打电话
        整组按钮离标题的距离由 .chat-nav-wrap 的 margin-left 控制；
        .chat-nav-wrap 同时是天气小窗口的定位参照（position: relative）
      -->
      <div class="chat-nav-wrap">
        <nav class="chat-nav">
          <button
            v-for="(btn, i) in navButtons"
            :key="btn.key"
            type="button"
            class="nav-btn"
            :class="{ 'nav-btn--active': i === activeNav }"
            :title="btn.hint"
            :aria-pressed="i === activeNav"
            @click="selectNav(i)"
          >
            <!-- 图标：直接用 path 画，不加载图片，选中时跟着文字一起变蓝 -->
            <svg
              class="nav-btn__icon"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
            >
              <path
                v-for="d in btn.paths"
                :key="d"
                :d="d"
                fill="none"
                stroke="currentColor"
                stroke-width="1.7"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
              <span class="nav-btn__text">{{ btn.text }}</span>
            </button>
        </nav>

        <!-- 天气小窗口：点「天气」按钮弹出，点空白 / Esc / × 关闭 -->
        <WeatherPanel
          v-if="showWeather"
          :initial-province="weatherProvince"
          :initial-city="weatherCity"
          @close="closeWeather"
          @update:place="saveWeatherPlace"
        />

        <!-- 打电话准备窗口：和天气一样挂在导航条下面 -->
        <CallPanel
          v-if="callStage === 'prompt'"
          @dial="dialCall"
          @close="callStage = 'idle'"
        />
      </div>

      <div class="chat-user-box">
        <span class="chat-user">{{ props.username }}</span>

        <!-- 右上角工具区：音量（点开才调） + 设置（填 API Key） -->
        <div class="header-tools">
          <!-- 余额：在音量左边，点开看明细 -->
          <BalanceWidget />

          <!-- 音量：点一下弹出小面板，里面才有滑块 -->
          <button
            class="tool-btn"
            :class="{ 'tool-btn--on': openMenu === 'volume', 'tool-btn--muted': muted }"
            :title="`音量：语音 ${voiceMuted ? '静音' : voiceVolume + '%'} / 音乐 ${muted ? '静音' : bgmVolume + '%'}`"
            :aria-expanded="openMenu === 'volume'"
            @click="toggleMenu('volume')"
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


          <!-- 设置：齿轮，点开可以填自己的 API Key -->
          <button
            class="tool-btn"
            :class="{ 'tool-btn--on': openMenu === 'settings' }"
            title="设置（API Key）"
            :aria-expanded="openMenu === 'settings'"
            @click="toggleMenu('settings')"
          >
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path
                d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.38a2 2 0 0 0-.73-2.73l-.15-.09a2 2 0 0 1-1-1.73v-.51a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"
              />
              <circle cx="12" cy="12" r="3.2" />
            </svg>
          </button>

          <!-- 两个小弹窗都挂在工具区里，以它为定位参照 -->
          <VolumeMenu
            v-if="openMenu === 'volume'"
            :bgm-volume="bgmVolume"
            :voice-volume="voiceMuted ? 0 : voiceVolume"
            :bgm-muted="muted"
            :voice-muted="voiceMuted"
            @update:bgm-volume="bgmVolume = $event"
            @update:voice-volume="voiceVolume = $event"
            @update:bgm-muted="muted = $event"
            @update:voice-muted="voiceMuted = $event"
            @close="openMenu = null"
          />
          <!-- AI 正在回复时锁住设置，避免一轮回复中途换模型 -->
          <SettingsMenu
            v-if="openMenu === 'settings'"
            :locked="isTyping"
            @close="openMenu = null"
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
        <MessageList
        :messages="messages"
        :is-typing="isTyping"
        :is-thinking="isThinking || callPending"
      />
        <MessageInput :disabled="isTyping" @send="sendMessage" />
      </section>
    </main>

    <!-- 行程面板：填出发地/目的地，用高德地图画路线 -->
    <RoutePlanner v-if="showRoute" @close="showRoute = false" />
    <PhoneCall
      v-if="showCall"
      ref="phoneRef"
      :voice-volume="voiceMuted ? 0 : voiceVolume"
      @close="closeCall"
    />
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
/* 外壳：负责定位（天气弹窗以它为参照）和离标题的距离 */
.chat-nav-wrap {
  position: relative;
  display: flex;
  margin-left: 48px;   /* ★ 整组按钮偏左的位置就在这调 */
  flex: 0 1 auto;
  min-width: 0;
}

.chat-nav {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 0 1 auto;
  overflow-x: auto;    /* 按钮太多时横向滚动，不挤爆导航条 */
}

/* 按钮本体：胶囊形，默认透明底白字，选中变白底蓝字（参考图效果） */
.nav-btn {
  flex: 0 0 auto;
  min-width: 84px;             /* 三个按钮等宽，图标+文字都放得下 */
  height: 32px;
  padding: 0 14px;
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid transparent;  /* 和选中态的描边同宽，避免选中时抖动 */
  border-radius: 16px;
  background: transparent;
  color: rgba(255, 255, 255, 0.92);
  font-size: 0.92rem;
  font-family: inherit;        /* 不继承的话 <button> 会用系统默认字体 */
  cursor: pointer;
  transition: background 0.2s, color 0.2s, border-color 0.2s;
}
.nav-btn:hover { background: rgba(255, 255, 255, 0.16); }
.nav-btn:focus-visible {
  outline: 2px solid #fffdf8;
  outline-offset: 2px;
}

/* 选中的按钮：白底蓝字 */
.nav-btn--active {
  background: #fffdf8;
  color: #3d7fd6;
  border-color: #fffdf8;
  font-weight: 500;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.16);
}
.nav-btn--active:hover { background: #fffdf8; }

/* 图标 / 文字两个槽位 */
.nav-btn__icon {
  flex: 0 0 auto;
  display: block;             /* svg 默认 inline，底部会多出几像素空隙 */
}
.nav-btn__text { white-space: nowrap; }

/* ---- 右侧用户区 ---- */
.chat-user-box {
  margin-left: auto;       /* 推到最右边 */
  display: flex;
  align-items: center;
  gap: 12px;
}
.chat-user { font-size: 0.95rem; opacity: 0.95; }

/* ---- 右上角工具按钮：音量 / 设置 ---- */
.header-tools {
  position: relative;      /* 音量、设置两个小弹窗以它为定位参照 */
  display: flex;
  align-items: center;
  gap: 4px;
}

.tool-btn {
  width: 30px;
  height: 30px;
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
.tool-btn:hover { background: rgba(255, 255, 255, 0.16); }
.tool-btn--on { background: rgba(255, 255, 255, 0.24); }
.tool-btn--muted { opacity: 0.6; }
.tool-btn:focus-visible {
  outline: 2px solid #fffdf8;
  outline-offset: 2px;
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
