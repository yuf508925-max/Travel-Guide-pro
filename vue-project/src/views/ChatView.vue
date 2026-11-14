<!-- ====================================================================
  ChatView —— 登录后的主页面（三块结构，对应你画的框）
    蓝框 = 顶部导航条：左边标题、中间一排选项按钮、右边用户 + 退出
    黄框 = 左侧：Live2D 小人舞台
    红框 = 右侧：和 AI 聊天的界面（消息列表 + 输入框）
==================================================================== -->

<script setup lang="ts">
import { computed, ref, shallowRef, watch, onMounted, onBeforeUnmount } from 'vue'
import MessageList from '../components/MessageList.vue'
import MessageInput from '../components/MessageInput.vue'
import Live2DStage from '../components/Live2DStage.vue'
import ClockWidget from '../components/ClockWidget.vue'
import WeatherPanel from '../components/WeatherPanel.vue'
import BalanceWidget from '../components/BalanceWidget.vue'
import MemoryPanel from '../components/MemoryPanel.vue'
import AnnouncementPanel from '../components/AnnouncementPanel.vue'
import MusicPlayer from '../components/MusicPlayer.vue'
import RoutePlanner from '../components/RoutePlanner.vue'
import VlogPanel from '../components/VlogPanel.vue'
import VideoFloat from '../components/VideoFloat.vue'
import type { VlogVideo } from '../types/vlog'
import { resetAmapConfig } from '../composables/useAmap'
import VolumeMenu from '../components/VolumeMenu.vue'
import SettingsMenu from '../components/SettingsMenu.vue'
import PhoneCall from '../components/PhoneCall.vue'
import CallPanel from '../components/CallPanel.vue'
import { useChatStream } from '../composables/useChatStream'
import { useConversations } from '../composables/useConversations'
import { useLipSync } from '../composables/useLipSync'
import { useAnnouncements } from '../composables/useAnnouncements'
import { useLive2DActor, type ChatTurn, type Live2DAction } from '../composables/useLive2DActor'

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

// model3.json 里定义的表情（Expressions），也当作"动作"给芙芙换脸/换道具
// 鱼鱼 / 汗 两个表情已经拿掉了：面板上不显示，AI 那边也不会再挑
const expressions = [
  '呆毛电风扇', '哭', '喝饮料', '大聪明',
  '小脸红', '帽子', '托脸', '拿勺子',
  '拿蛋糕', '捂嘴', '星星',
  '猫猫嘴', '生气', '走路切换',
]

function triggerMotion(group: string, index: number, fromAi = false) {
  // AI 控制模式下动作归大模型管，手动按钮一律不响应（按钮本身也是 disabled，
  // 这里再拦一道，防止键盘回车/残留点击偷偷改掉她的表演）
  if (aiMode.value && !fromAi) return
  // 「待机」是自动循环的默认动画，直接 playMotion('Idle') 会被库拒绝，
  // 所以走专用的 resetToIdle：先停掉当前动作，再从头重播待机。
  if (group === 'Idle') {
    live2dRef.value?.resetToIdle()
  } else {
    live2dRef.value?.playMotion(group, index)
  }
}

function triggerExpression(name: string, fromAi = false) {
  if (aiMode.value && !fromAi) return
  live2dRef.value?.setExpression(name)
}

function toggleActions() {
  showActions.value = !showActions.value
}

// ------------------------------------------------------------------
// AI 控制模式
//   开：芙芙自己挑表情/动作（每轮回复后问一次大模型），眼睛不再跟着鼠标
//   关：还是原来那套手动按钮
// ------------------------------------------------------------------
// 动作名归一化：大模型可能回组名（TapBody），也可能回面板上的中文标签（摊手）
const MOTION_ALIASES: Record<string, string> = {
  Idle: 'Idle',
  待机: 'Idle',
  TapBody: 'TapBody',
  摊手: 'TapBody',
  变芒: '变芒',
  变荒: '变荒',
}

// 口型同步：把正在播的 TTS 音量逐帧写进 ParamMouthOpenY
const lipSync = useLipSync((v) => live2dRef.value?.setMouthOpen(v))

const actor = useLive2DActor()
const aiMode = actor.aiMode

/** 大模型挑完了，落到模型上。先播动作再换表情：
 *  变芒/变荒/待机这些动作会 resetAllParameters + resetExpression，
 *  顺序反了刚换上的表情会被动作复位掉。 */
function applyAiAction(action: Live2DAction) {
  if (!aiMode.value) return
  const group = action.motion ? MOTION_ALIASES[action.motion] : ''
  if (group) triggerMotion(group, 0, true)
  if (action.expression) triggerExpression(action.expression, true)
}

/** 当前对话里最后一条 AI 回复 / 用户消息 */
function lastAiText(): string {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const m = messages.value[i]
    if (m?.role === 'ai') return (m.text ?? '').trim()
  }
  return ''
}

function lastUserText(): string {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const m = messages.value[i]
    if (m?.role === 'user') return (m.text ?? '').trim()
  }
  return ''
}

/** 请大模型挑表情/动作时要看的上下文：当前对话最近 8 条消息。
 *  注意只读 messages（= 当前激活的那条对话），切到别的对话就是别的数组。 */
function recentHistory(): ChatTurn[] {
  const turns: ChatTurn[] = []
  for (let i = messages.value.length - 1; i >= 0 && turns.length < 8; i -= 1) {
    const m = messages.value[i]
    const text = (m?.text ?? '').trim()
    if (!m || !text) continue
    turns.unshift({ role: m.role, text: text.slice(0, 400) })
  }
  return turns
}

/**
 * 请大模型挑一个表情/动作（模式关着时内部会直接返回空）。
 * @param idle true = 挂机一分钟的自发小表情，此刻没有新台词
 *
 * 隔离：这里记下提问时属于哪个对话，结果回来如果对话已经切走就丢弃——
 * 否则旧对话的表情会跑到新对话里，还白打断新的表演。
 */
/** 每条对话上一轮演过的动作/表情。
 *  只用来告诉大模型「别又挑这个」——分开存，切对话不会互相影响。 */
const lastActionByConv = new Map<number, Live2DAction>()

// 模型有时候嘴硬，连着两轮给同一个表情；这时从前几个温和的表情里随便换一个，
// 至少让人看得出来"她换表情了"，而不是以为功能坏了。
const GENTLE_FALLBACKS = ['小脸红', '猫猫嘴', '星星', '托脸', '捂嘴', '大聪明']

function pickDifferentExpression(prev: string | null): string {
  const pool = GENTLE_FALLBACKS.filter((n) => n !== prev && expressions.includes(n))
  const pick = pool[Math.floor(Math.random() * pool.length)]
  return pick ?? ''
}

async function askForAction(idle = false, replyOverride = '') {
  if (!aiMode.value) return

  const convId = currentConversationId.value
  const reply = idle ? '' : (replyOverride || lastAiText())
  if (!idle && !reply) return
  // 挂机触发时如果她正好在说话/打电话，就别抢戏了
  if (idle && (isTyping.value || showCall.value)) return

  const prev = convId == null ? null : lastActionByConv.get(convId)
  const action = await actor.request({
    reply,
    user: idle ? '' : lastUserText(),
    history: recentHistory(),
    idle,
    previous: prev ? { motion: prev.motion, expression: prev.expression } : null,
  })
  if (!action) return
  if (convId !== currentConversationId.value || !aiMode.value) return

  // 跟上一轮一模一样（动作+表情都没变）就兜个底，换个温和的表情
  if (prev && !idle && action.motion === prev.motion && action.expression === prev.expression) {
    const alt = pickDifferentExpression(prev.expression)
    if (alt) action.expression = alt
  }

  applyAiAction(action)
  if (convId != null) lastActionByConv.set(convId, action)
  resetIdleTimer()
}

function toggleAiMode() {
  aiMode.value = !aiMode.value
  // 刚打开时先就着当前上下文演一个，不用干等下一轮
  if (aiMode.value) {
    void askForAction()
    resetIdleTimer()
  } else {
    clearIdleTimer()
  }
}

const props = defineProps({
  username: { type: String, default: '' },
})
const emit = defineEmits(['logout'])

// 聊天逻辑全部在 useChatStream 里（发消息、假流式回复、消息列表）
// 界面组件只负责展示，互相之间靠 props 和事件传话
// ------------------------------------------------------------------
// 每个对话一个独立的流实例
//   · 切走时旧对话的流继续跑，输入框只受「当前对话」的 isTyping 锁
//   · 切回来还能看到那条回复的完整内容
// ------------------------------------------------------------------
type ChatStream = ReturnType<typeof useChatStream>

const streams = new Map<number, ChatStream>()
const stream = shallowRef<ChatStream>(useChatStream())

const currentConversationId = ref<number | null>(null)

// 切对话 / 刚打开页面时，历史文字直接显示（不做逐个冒泡），
// 等用户真的发了一条消息再恢复动画
const suppressBubble = ref(true)

const messages = computed(() => stream.value.messages.value)
const isTyping = computed(() => stream.value.isTyping.value)
const isThinking = computed(() => stream.value.isThinking.value)
// 芙芙正在调工具（查天气 / 查车次 / 算路线）时的那句提示
const toolHint = computed(() => stream.value.toolHint.value)
const holdAi = stream.value.holdAi

function sendMessage(text: string) {
  suppressBubble.value = false
  void stream.value.sendMessage(text)
}

function takeHeld() {
  return stream.value.takeHeld()
}

function streamFor(id: number | null): ChatStream {
  if (!id) return stream.value
  let s = streams.get(id)
  if (!s) {
    s = useChatStream()
    s.currentConversationId.value = id
    streams.set(id, s)
  }
  return s
}

/** 把当前激活的流换成某个对话的流 */
function activateStream(id: number | null) {
  stream.value = streamFor(id)
}

// ------------------------------------------------------------------
// 多个对话：每条对话各自一份记忆（后端只存摘要）
// ------------------------------------------------------------------
const {
  conversations,
  load: loadConversations,
  create: createConversation,
  rename: renameConversation,
  remove: deleteConversation,
  summarize,
} = useConversations()

const showMemory = ref(false)

// 公告：顶栏红点看「有没有没看过的」，打开面板即全部标为已读
const showNotice = ref(false)
const { unreadCount: noticeUnread, loadNotices } = useAnnouncements()

const convOpen = ref(false)
const renamingId = ref<number | null>(null)
const renameDraft = ref('')

const currentTitle = computed(
  () => conversations.value.find((c) => c.id === currentConversationId.value)?.title ?? '对话',
)

function snapshot() {
  return messages.value.map((m) => ({ role: m.role, text: m.text }))
}

/**
 * 把当前这段对话压成摘要存进它自己的记录（切走 / 关网页时调）。
 * 注意：这里**不 await**——摘要要走一次模型调用（1~3 秒），
 * 让它去后台跑，界面该切就立刻切。
 */
function saveCurrent(keepalive = false) {
  const id = currentConversationId.value
  if (!id) return
  const all = snapshot()
  // 只把「上次总结之后新增的那一段」发上去，避免重复计费 / 重复写记忆
  const done = conversations.value.find((c) => c.id === id)?.summarized_upto ?? 0
  const msgs = all.slice(done)
  if (msgs.filter((m) => m.text.trim()).length < 2) return
  void summarize(id, msgs, keepalive).catch(() => '')
}

/**
 * 每凑够 10 条就总结一次（中途也记，不等关网页）。
 * 由 ChatView 在「一条回复结束」时调用。
 */
const SUMMARY_EVERY = 10
function maybeSummarize() {
  const id = currentConversationId.value
  if (!id) return
  const done = conversations.value.find((c) => c.id === id)?.summarized_upto ?? 0
  if (snapshot().length - done >= SUMMARY_EVERY) saveCurrent()
}

function switchConv(id: number) {
  if (id === currentConversationId.value) {
    convOpen.value = false
    return
  }
  saveCurrent()

  // 换到目标对话自己的流：它的输入框是否锁，只看它自己有没有在回复
  currentConversationId.value = id
  suppressBubble.value = true
  activateStream(id)
  localStorage.setItem('fufu-conversation', String(id))
  convOpen.value = false

  // 但语音要停：继续念旧对话的内容会串台
  if (showCall.value || callStage.value === 'active') closeCall()
}

async function newConv() {
  saveCurrent()
  const item = await createConversation('新的对话')
  currentConversationId.value = item.id
  suppressBubble.value = true
  activateStream(item.id)
  localStorage.setItem('fufu-conversation', String(item.id))
  if (showCall.value || callStage.value === 'active') closeCall()
  // 菜单不关：紧接着弹出重命名输入框，让用户直接给新对话起名
  renamingId.value = item.id
  renameDraft.value = ''
}

function startRename(id: number) {
  const target = conversations.value.find((c) => c.id === id)
  renamingId.value = id
  renameDraft.value = target?.title ?? ''
}

async function commitRename() {
  const id = renamingId.value
  const title = renameDraft.value.trim()
  renamingId.value = null
  if (!id || !title) return
  await renameConversation(id, title).catch(() => null)
}

async function removeConv(id: number) {
  if (!window.confirm('删除这个对话？它记住的内容会一起删掉。')) return
  await deleteConversation(id).catch(() => null)
  streams.delete(id)
  if (id !== currentConversationId.value) return

  const next = conversations.value[0]
  if (next) {
    currentConversationId.value = next.id
    suppressBubble.value = true
  activateStream(next.id)
    localStorage.setItem('fufu-conversation', String(next.id))
    if (showCall.value || callStage.value === 'active') closeCall()
    return
  }

  // 一个都不剩：开一个新的空对话
  const item = await createConversation('新的对话').catch(() => null)
  if (!item) return
  currentConversationId.value = item.id
  activateStream(item.id)
  localStorage.setItem('fufu-conversation', String(item.id))
}

const onPageLeave = () => {
  void saveCurrent(true)
}

const onVisibilityLeave = () => {
  if (document.visibilityState === 'hidden') void saveCurrent(true)
}

async function initConversations() {
  const list = await loadConversations().catch(() => [])
  if (!list.length) {
    const item = await createConversation('新的对话').catch(() => null)
    if (item) {
      currentConversationId.value = item.id
      activateStream(item.id)
      localStorage.setItem('fufu-conversation', String(item.id))
    }
    return
  }
  const saved = Number(localStorage.getItem('fufu-conversation') || 0)
  const pick = list.find((c) => c.id === saved) ?? list[0]
  if (!pick) return
  currentConversationId.value = pick.id
  suppressBubble.value = true
  activateStream(pick.id)
  localStorage.setItem('fufu-conversation', String(pick.id))
}

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
    key: 'vlog',
    text: '观看vlog',
    hint: '看 B 站上和这个地区相关的旅行 vlog（点开是浮窗播放器）',
    // 播放键：圆角方框 + 中间的三角，表示"看视频"
    paths: [
      'M6.5 3.5h11A3 3 0 0 1 20.5 6.5v11a3 3 0 0 1-3 3h-11a3 3 0 0 1-3-3v-11a3 3 0 0 1 3-3Z',
      'M10 8.6v6.8l5.6-3.4Z',
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
// 观看 vlog 面板（B 站旅行视频）
const showVlog = ref(false)
// 正在浮窗里播放的视频；null = 没开播放器
const activeVideo = ref<VlogVideo | null>(null)

/** 点 vlog 卡片：开浮窗播放器（面板关掉它也不停） */
function openVideo(video: VlogVideo) {
  activeVideo.value = video
}
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

// 把「通话期间攒着没显示」的文字一次性放出来（所有对话的流都要放，
// 否则切走那条对话的回复会永远停在一半）
function flushAllHeld() {
  const all = [stream.value, ...streams.values()]
  for (const s of all) {
    const held = s.takeHeld()
    if (held) held.message.text = held.text
  }
}

function closeCall() {
  showCall.value = false
  callStage.value = 'idle'
  lipSync.stop()   // 挂断后别再让嘴动（音频会被 PhoneCall 卸载时停掉）
  flushAllHeld()
}

// ------------------------------------------------------------------
// 挂机一分钟：她安静待着的时候，自己按当前对话的上下文换个表情
//   - 计时只在「当前这条对话」里有效：切对话就归零，旧对话的计时器不会打到新对话身上
//   - 正在打字 / 正在打电话 / 没开 AI 模式 都不计时
// ------------------------------------------------------------------
const IDLE_ACTION_MS = 60_000
let idleTimer = 0

function clearIdleTimer() {
  if (idleTimer) {
    clearTimeout(idleTimer)
    idleTimer = 0
  }
}

function resetIdleTimer() {
  clearIdleTimer()
  if (!aiMode.value) return
  if (isTyping.value || showCall.value) return
  if (!currentConversationId.value) return
  // 还没聊过任何东西就没什么上下文可演，等有消息了 watcher 会再进来
  if (recentHistory().length === 0) return
  idleTimer = window.setTimeout(async () => {
    idleTimer = 0
    await askForAction(true)
    // 换成功了 askForAction 已经重新计时；没换成（网络/模型抽风）就自己续上，
    // 否则一次失败之后再也不会挂机触发了
    if (!idleTimer && aiMode.value && !isTyping.value && !showCall.value) resetIdleTimer()
  }, IDLE_ACTION_MS)
}

// 任何"新动静"都重新开始数 60 秒
watch(
  [aiMode, currentConversationId, isTyping, () => messages.value.length, showCall],
  () => resetIdleTimer(),
)

// 切对话：旧对话在路上的动作请求直接掐掉，免得回来时演在新对话里
watch(currentConversationId, () => {
  actor.cancel()
})

// 标签页藏起来的时候不用演；切回来重新数 60 秒
function onVisibilityIdle() {
  if (document.hidden) clearIdleTimer()
  else resetIdleTimer()
}

function selectNav(index: number) {
  const key = navButtons.value[index]?.key
  openMenu.value = null

  // 电话：先弹出一个"拨出"图标，点那个图标才真正拨号
  if (key === 'tts') {
    showWeather.value = false
    showRoute.value = false
    showVlog.value = false
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
    showVlog.value = false
    showWeather.value = !showWeather.value
    activeNav.value = index
    return
  }

  // 行程：打开路线规划面板（高德地图）
  if (key === 'trip') {
    showWeather.value = false
    showVlog.value = false
    showRoute.value = !showRoute.value
    activeNav.value = index
    return
  }

  // 观看 vlog：打开 B 站视频面板
  if (key === 'vlog') {
    showWeather.value = false
    showRoute.value = false
    showVlog.value = !showVlog.value
    activeNav.value = index
    return
  }

  // 其它按钮：先只切高亮，并把天气窗口收起来
  showWeather.value = false
  showRoute.value = false
  activeNav.value = index
  // TODO: 以后在这里根据 key 打开对应面板：
  //   tts → 语音通话（已在上面的分支里处理）
}

// ------------------------------------------------------------------
// 音量控制
//   现在控制的是背景音乐（public 下的 "Travelers' encore - Andrew Prahlow.mp3"）。
//   以后接了语音合成（TTS），把语音那个 <audio> 也接到 applyVolume 里就行：
//     ① 控制 TTS 播放的 <audio>：ttsAudio.volume = volume.value / 100
//     ② 或每帧 setMouthOpen 时，同步给 Web Audio 的 gainNode.gain.value（声音总闸 + 口型）
// ------------------------------------------------------------------
const BGM_SRC = "/Travelers' encore - Andrew Prahlow.mp3"

const bgmVolume = ref(20)    // 背景音乐 0~100
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

// 右上角「音乐」开始放用户自己的歌时，先把自带的 BGM 停掉，免得两首一起响
function pauseBgm() {
  audioRef.value?.pause()
}

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
  // 一轮回复结束：凑够 10 条就把新增的这段压成记忆（后台跑，不阻塞界面）
  if (!typing) maybeSummarize()

  if (typing) {
    // 通话中：正文还在生成，继续显示思考提示
    if (showCall.value) callPending.value = true
    return
  }

  // 非通话：这轮文字已经收全，问一下大模型该摆什么表情/动作
  if (!showCall.value) {
    askForAction()
    return
  }

  const held = takeHeld()
  if (!held) return

  const { message, text } = held
  message.text = ''
  // 通话里文字被 held 着，lastAiText() 读不到，直接把整段交过去
  void askForAction(false, text)
  const duration = (await phoneRef.value?.speakAll(text)) ?? 0
  // 语音已经开口，让嘴跟着音量动起来；时长做兜底，防止 ended 事件丢失
  lipSync.start(phoneRef.value?.getAudio() ?? null, duration)
  // 撤掉思考提示，文字跟着音频节奏跳出来
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

onMounted(async () => {
  await initConversations()
  window.addEventListener('pagehide', onPageLeave)
  document.addEventListener('visibilitychange', onVisibilityLeave)
  document.addEventListener('visibilitychange', onVisibilityIdle)

  applyVolume()
  tryPlay()
  // 公告红点：进页面先拉一次列表（拿不到就当没有公告）
  void loadNotices()
  document.addEventListener('pointerdown', resumeOnFirstGesture)
  // 页面加载完可能已经是 AI 模式（存了 localStorage），先把 60 秒计时支起来
  resetIdleTimer()
})
onBeforeUnmount(() => {
  window.removeEventListener('pagehide', onPageLeave)
  document.removeEventListener('visibilitychange', onVisibilityLeave)
  document.removeEventListener('visibilitychange', onVisibilityIdle)
  clearIdleTimer()
  actor.cancel()
  void saveCurrent(true)

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

        <MemoryPanel
          v-if="showMemory"
          :initial-conversation="currentConversationId"
          @close="showMemory = false"
        />

        <!-- 公告：管理员在后台发的通知 -->
        <AnnouncementPanel v-if="showNotice" @close="showNotice = false" />
      </div>

      <div class="chat-user-box">
        <span class="chat-user">{{ props.username }}</span>

        <!-- 公告：管理员发的通知，有没看过的就亮个小红点 -->
        <button
          class="notice-btn"
          :class="{ 'notice-btn--unread': noticeUnread > 0 }"
          type="button"
          :title="noticeUnread > 0 ? `公告：${noticeUnread} 条没看过` : '公告'"
          @click="showNotice = true"
        >
          <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
            <path
              d="M12 5.5c-2.4 0-4.3 1.9-4.3 4.3v3.1l-1.4 2.3c-.2.4.1.9.5.9h10.4c.4 0 .7-.5.5-.9l-1.4-2.3V9.8c0-2.4-1.9-4.3-4.3-4.3Z"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linejoin="round"
            />
            <path
              d="M10.3 18.2a1.8 1.8 0 0 0 3.4 0"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
            />
          </svg>
          <span>公告</span>
          <span v-if="noticeUnread > 0" class="notice-btn__dot">
            {{ noticeUnread > 9 ? '9+' : noticeUnread }}
          </span>
        </button>

        <!-- 音乐：上传自己的歌（只在本机临时目录，退出登录清空） -->
        <MusicPlayer :volume="bgmVolume" :muted="muted" @play="pauseBgm" />

        <!-- 记忆：点开看芙芙记住了什么 -->
        <button
          class="mem-btn"
          type="button"
          title="记忆：芙芙记住的事"
          @click="showMemory = true"
        >
          <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
            <path
              d="M12 4.2c-3 0-5.3 2.1-5.3 4.9 0 1.2-.5 1.8-1.2 2.6-.5.6-.2 1.5.6 1.7.6.2 1 .4 1.1 1.1.3 1.9 2.1 3.3 4.4 3.3 1.3 0 2.4-.4 3.2-1.1"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
            />
            <circle cx="7.1" cy="9.4" r="1" fill="currentColor" />
            <circle cx="10.2" cy="7.1" r="1" fill="currentColor" />
            <circle cx="13.8" cy="7.1" r="1" fill="currentColor" />
            <circle cx="16.9" cy="9.4" r="1" fill="currentColor" />
          </svg>
          <span>记忆</span>
        </button>


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
        <Live2DStage
          ref="live2dRef"
          model-url="/芙宁娜（vts）/芙宁娜.model3.json"
          :follow-mouse="!aiMode"
        />

        <!-- 左上角时钟：时:分 + 小秒 + 日期 -->
        <ClockWidget />

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
            <!-- AI 控制中：手动按钮全部锁掉，避免和大模型抢着改表情 -->
            <p v-if="aiMode" class="live2d-actions__locked">
              AI 控制中 · 手动动作/表情已锁定；60 秒没动静她会自己换个表情。点下面的按钮可退出
            </p>

            <!-- 动作分组 -->
            <span class="live2d-actions__label">动作</span>
            <button
              v-for="m in motions"
              :key="m.group"
              class="live2d-actions__btn"
              type="button"
              :disabled="aiMode"
              :title="aiMode ? 'AI 控制中，动作由芙芙自己决定' : ''"
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
                type="button"
                :disabled="aiMode"
                :title="aiMode ? 'AI 控制中，表情由芙芙自己决定' : ''"
                @click="triggerExpression(name)"
              >
                {{ name }}
              </button>
            </div>

            <!-- 分隔线 -->
            <div class="live2d-actions__divider"></div>

            <!-- AI 控制：开着时按钮高亮，每轮回复结束由大模型挑表情/动作 -->
            <button
              class="live2d-actions__btn live2d-actions__btn--ai"
              :class="{ 'live2d-actions__btn--on': aiMode }"
              type="button"
              :title="aiMode
                ? `AI 控制中${actor.lastAction.value?.reason ? '：' + actor.lastAction.value.reason : ''}（点一下关掉）`
                : 'AI 控制：芙芙结合当前对话自己换表情/动作，眼睛不再跟着鼠标，挂机一分钟也会自己换一次'"
              @click="toggleAiMode"
            >
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
              AI 控制{{ aiMode ? ' · 开' : '' }}
            </button>
          </div>
        </div>
      </section>
      

      <!-- 红框：聊天面板 = 消息列表 + 输入框，上下拼起来 -->
      <section class="chat-panel">
        <!-- 对话切换：多条对话，各自一份记忆 -->
        <div class="conv-wrap">
          <button
            class="conv-btn"
            :class="{ 'conv-btn--on': convOpen }"
            type="button"
            :title="`当前对话：${currentTitle}`"
            @click="convOpen = !convOpen"
          >
            <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
              <path
                d="M4.5 5.5h15v10h-8.2L7 19v-3.5H4.5z"
                fill="none"
                stroke="currentColor"
                stroke-width="1.7"
                stroke-linejoin="round"
              />
            </svg>
            <span class="conv-btn__title">{{ currentTitle }}</span>
            <span class="conv-btn__caret">▾</span>
          </button>

          <div v-if="convOpen" class="conv-menu">
            <div class="conv-menu__head">
              <span>对话 · {{ conversations.length }}</span>
              <button class="conv-new" type="button" @click="newConv">＋ 新建</button>
            </div>

            <ul class="conv-list">
              <li
                v-for="c in conversations"
                :key="c.id"
                class="conv-item"
                :class="{ 'conv-item--on': c.id === currentConversationId }"
              >
                <button class="conv-item__pick" type="button" @click="switchConv(c.id)">
                  <span class="conv-item__title">{{ c.title }}</span>
                  <span class="conv-item__meta">{{ c.summary ? '有记忆' : '暂无记忆' }}</span>
                </button>
                <button class="conv-item__act" type="button" title="重命名" @click.stop="startRename(c.id)">✎</button>
                <button
                  class="conv-item__act conv-item__act--del"
                  type="button"
                  title="删除"
                  @click.stop="removeConv(c.id)"
                >✕</button>
              </li>
            </ul>

            <div v-if="renamingId !== null" class="conv-rename">
              <input
                v-model="renameDraft"
                maxlength="40"
                placeholder="给这个对话起个名字"
                @keyup.enter="commitRename"
              />
              <button type="button" class="conv-rename__ok" @click="commitRename">保存</button>
              <button type="button" class="conv-rename__no" @click="renamingId = null">取消</button>
            </div>

            <p class="conv-menu__tip">换对话不会打断正在生成的回复，但会挂断语音。</p>
          </div>
        </div>
        <MessageList
        :messages="messages"
        :is-typing="isTyping"
        :is-thinking="isThinking || callPending"
        :tool-hint="toolHint"
        :suppress-animation="suppressBubble"
      />
        <MessageInput :disabled="isTyping" @send="sendMessage" />
      </section>
    </main>

    <!-- 行程面板：填出发地/目的地，用高德地图画路线 -->
    <RoutePlanner v-if="showRoute" @close="showRoute = false" />

    <!-- 观看 vlog：5 条 B 站视频卡片；点卡片 → 右下角浮窗播放器 -->
    <VlogPanel
      v-if="showVlog"
      :initial-region="weatherCity"
      @close="showVlog = false"
      @open="openVideo"
    />
    <!-- 浮窗播放器：不放在 VlogPanel 里面，这样关掉面板视频还能继续看 -->
    <VideoFloat v-if="activeVideo" :video="activeVideo" @close="activeVideo = null" />

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
.mem-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 10px;
  border: 1px solid rgba(200, 240, 255, 0.35);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
  color: #eaf8ff;
  font-size: 0.76rem;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease;
}

.mem-btn:hover {
  background: rgba(255, 255, 255, 0.22);
  border-color: rgba(220, 250, 255, 0.6);
}

/* 公告按钮：和「记忆」同一套外观，右边跟一个未读数小圆点 */
.notice-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 10px;
  border: 1px solid rgba(200, 240, 255, 0.35);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
  color: #eaf8ff;
  font-size: 0.76rem;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease;
}

.notice-btn:hover {
  background: rgba(255, 255, 255, 0.22);
  border-color: rgba(220, 250, 255, 0.6);
}

.notice-btn--unread {
  border-color: rgba(255, 176, 190, 0.75);
}

.notice-btn__dot {
  position: absolute;
  top: -5px;
  right: -6px;
  min-width: 15px;
  height: 15px;
  padding: 0 3px;
  border-radius: 999px;
  background: #ff6b81;
  color: #fff;
  font-size: 0.6rem;
  line-height: 15px;
  text-align: center;
  box-shadow: 0 0 0 2px rgba(40, 88, 108, 0.9);
}

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
/* AI 控制模式下手动按钮锁掉 */
.live2d-actions__btn:disabled,
.live2d-actions__btn:disabled:hover {
  opacity: 0.32;
  background: transparent;
  border-color: rgba(255, 253, 248, 0.45);
  cursor: not-allowed;
}
.live2d-actions__locked {
  margin: 0 0 2px;
  font-size: 0.74rem;
  line-height: 1.5;
  color: rgba(255, 253, 248, 0.72);
}

/* 分隔线 */
.live2d-actions__divider {
  height: 1px;
  margin: 2px 2px;
  background: rgba(255, 253, 248, 0.25);
}

/* AI 控制按钮：关=虚线描边，开=实心高亮 */
.live2d-actions__btn--ai {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border-style: dashed;
}
.live2d-actions__btn--ai:hover {
  border-color: rgba(255, 253, 248, 0.75);
}
.live2d-actions__btn--on,
.live2d-actions__btn--on:hover {
  background: #fffdf8;
  border-style: solid;
  border-color: #fffdf8;
  color: #1f3b3a;
  font-weight: 600;
  box-shadow: 0 0 0 3px rgba(255, 253, 248, 0.2);
}

/* ---- 红框：聊天面板 ---- */
.chat-panel {
  position: relative;      /* 对话按钮定位在面板右上角 */
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

/* ---------------- 对话切换（多对话 + 每对话一份记忆） ---------------- */
.conv-wrap {
  position: absolute;
  top: 10px;
  right: 12px;
  z-index: 6;
}

.conv-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 220px;
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid rgba(150, 230, 255, 0.28);
  background: rgba(6, 34, 44, 0.55);
  color: #d8f6ff;
  font-size: 0.78rem;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.conv-btn:hover,
.conv-btn--on {
  border-color: rgba(150, 230, 255, 0.6);
  background: rgba(12, 58, 70, 0.75);
}

.conv-btn__title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-btn__caret {
  opacity: 0.7;
  font-size: 0.7rem;
}

.conv-menu {
  position: absolute;
  z-index: 30;
  top: calc(100% + 10px);
  right: 0;
  left: auto;
  width: 320px;
  padding: 10px;
  border-radius: 14px;
  border: 1px solid rgba(150, 230, 255, 0.22);
  background: #0a262b;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
}

.conv-menu__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 0.75rem;
  color: #9fd8e6;
}

.conv-new {
  border: 1px solid rgba(150, 230, 255, 0.35);
  background: transparent;
  color: #8ff0c8;
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 0.72rem;
  cursor: pointer;
}

.conv-new:hover {
  background: rgba(143, 240, 200, 0.12);
}

.conv-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 260px;
  overflow-y: auto;
  margin: 0;
  padding: 0;
  list-style: none;
}

.conv-item {
  display: flex;
  align-items: center;
  gap: 4px;
  border-radius: 10px;
  padding: 2px 2px 2px 0;
}

.conv-item--on {
  background: rgba(143, 240, 200, 0.1);
}

.conv-item__pick {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 7px 9px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: #dff6fb;
  text-align: left;
  cursor: pointer;
}

.conv-item__pick:hover {
  background: rgba(150, 230, 255, 0.08);
}

.conv-item__title {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.82rem;
}

.conv-item__meta {
  font-size: 0.68rem;
  color: #7fb3c2;
}

.conv-item__act {
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #8fc6d4;
  font-size: 0.75rem;
  cursor: pointer;
}

.conv-item__act:hover {
  background: rgba(150, 230, 255, 0.12);
  color: #dff6fb;
}

.conv-item__act--del:hover {
  background: rgba(255, 110, 120, 0.16);
  color: #ffb3b8;
}

.conv-rename {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.conv-rename input {
  flex: 1;
  min-width: 0;
  padding: 6px 9px;
  border-radius: 8px;
  border: 1px solid rgba(150, 230, 255, 0.28);
  background: rgba(4, 24, 30, 0.9);
  color: #e6fbff;
  font-size: 0.78rem;
  outline: none;
}

.conv-rename input:focus {
  border-color: rgba(143, 240, 200, 0.7);
}

.conv-rename__ok,
.conv-rename__no {
  border-radius: 8px;
  border: 1px solid rgba(150, 230, 255, 0.28);
  background: transparent;
  color: #cfeff7;
  font-size: 0.74rem;
  padding: 0 10px;
  cursor: pointer;
}

.conv-rename__ok {
  border-color: rgba(143, 240, 200, 0.5);
  color: #8ff0c8;
}

.conv-menu__tip {
  margin: 8px 2px 0;
  font-size: 0.68rem;
  color: #7fb3c2;
  line-height: 1.5;
}

</style>
