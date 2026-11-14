<!-- ====================================================================
  Live2DStage —— 左边的 Live2D 小人舞台（黄框那块区域）
  做的事：
    1. 用 PixiJS 建一块透明画布（透出背后的海洋视频）
    2. 加载一个 Live2D 模型，自动缩放居中
    3. 没有模型时显示一个虚线占位框 —— 页面不会白屏
==================================================================== -->

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as PIXI from 'pixi.js'
// 从 /cubism4 子路径导入：只引入 Cubism 4 的内核支持，打包体积更小
// Cubism 4 内核向下兼容 Cubism 3 模型，市面上绝大多数模型都能跑
import { Live2DModel } from 'pixi-live2d-display/cubism4'

// pixi-live2d-display 内部会去 window.PIXI.Ticker 上挂动画刷新，所以先把 PIXI 挂出去
// 少了这一步，模型能出来但不会动（呼吸、眨眼全都没）
declare global {
  interface Window {
    PIXI: typeof PIXI
  }
}
window.PIXI = PIXI

const props = withDefaults(
  defineProps<{
    // 模型文件路径。把模型整个文件夹丢进 public/live2d/ 下面，
    // 然后把这个路径指到里面的 xxx.model3.json 就能换人
    modelUrl?: string
    // 眼睛要不要跟着鼠标转。AI 控制模式下传 false：
    // 否则她一边按 AI 挑的表情演，一边眼珠还在追鼠标，很出戏
    followMouse?: boolean
  }>(),
  { modelUrl: '/live2d/index.model3.json', followMouse: true }
)

const stageRef = ref<HTMLElement | null>(null)      // 外层容器 div，用来量尺寸
const canvasRef = ref<HTMLCanvasElement | null>(null) // canvas 元素，PixiJS 往这上画

// 状态：loading 加载中 / ready 已显示 / error 模型没找到（显示占位框）
const status = ref<'loading' | 'ready' | 'error'>('loading')

let app: PIXI.Application | null = null      // PixiJS 应用实例
let model: Live2DModel | null = null         // Live2D 模型实例
let resizeObserver: ResizeObserver | null = null // 尺寸监听器

// ------------------------------------------------------------------
// layoutModel：把模型摆正 —— 水平垂直居中，并按容器大小整体缩放
// 窗口拖动、容器变宽变窄都会调用它
// ------------------------------------------------------------------
function layoutModel() {
  if (!app || !model) return
  // 注意：renderer.width 是"物理像素"，除以 resolution 才是 CSS 尺寸
  const w = app.renderer.width / app.renderer.resolution
  const h = app.renderer.height / app.renderer.resolution

  // ★ 注意：这里绝对不能用 model.width / model.height 来算缩放！
  //   它俩会跟着"当前 scale"一起变，而 layoutModel() 每次容器尺寸变化都会被调用，
  //   于是算出来的 scale 会一轮一轮震荡（360 → 1.0 → 3000 → …），小人就越放越大。
  //   正确做法：取模型画布本身的固定尺寸 getSize()（不含缩放）。
  const internal = model.internalModel as unknown as { getSize?: () => [number, number] }
  const [modelW, modelH] = internal.getSize?.() ?? [1, 1]

  model.anchor.set(0.5, 0.5)   // 以模型中心对齐坐标点
  model.position.set(w / 2, h / 2)

  // 取宽高比例的较小值，保证模型完整塞进容器；0.92 留一点边距
  model.scale.set(Math.min(w / modelW, h / modelH) * 0.92)
}

// ------------------------------------------------------------------
// fixClippingMaskBuffer：修"遮罩数量过多"的模型
// ------------------------------------------------------------------
// 背景：Live2D 用"裁剪遮罩"（clipping mask）来实现头发盖住脸、衣服盖住身体这类遮挡。
//   pixi-live2d-display 创建渲染器时，把遮罩纹理数量写死成了 1 张 —— 而 1 张最多只能装
//   36 个遮罩。芙宁娜这个模型的 85 个遮罩远超上限，于是渲染直接抛异常，画面上什么都没有。
// 做法：模型初始化完之后，从裁剪管理器里读出真实遮罩数量，按官方 SDK 的规则
//   （每张遮罩纹理放 32 个）算出需要几张，再用正确数量把渲染器重新初始化一次。
// 注意：这依赖库的内部字段，将来升级 pixi-live2d-display 后若已修复，可以整段删掉。
// ------------------------------------------------------------------
function fixClippingMaskBuffer(target: Live2DModel) {
  // 库内部结构没暴露类型，这里按需断言
  const internal = target.internalModel as unknown as {
    renderer?: {
      initialize: (model: unknown, maskBufferCount: number) => void
      setIsPremultipliedAlpha: (v: boolean) => void
      _clippingManager?: { _clippingContextListForMask?: unknown[] }
    }
    coreModel?: unknown
  }

  const renderer = internal?.renderer
  const maskCount = renderer?._clippingManager?._clippingContextListForMask?.length ?? 0
  if (!renderer || maskCount <= 36) return // 36 = 单张遮罩纹理的上限，够用就不动

  const bufferCount = Math.ceil(maskCount / 32)
  console.warn(
    `[Live2D] 模型有 ${maskCount} 个裁剪遮罩，超过单张纹理上限（36），` +
      `改用 ${bufferCount} 张遮罩纹理重新初始化渲染器`
  )
  renderer.initialize(internal.coreModel, bufferCount)
  renderer.setIsPremultipliedAlpha(true)
}

// ------------------------------------------------------------------
// applyFollowMouse：眼睛到底跟不跟鼠标
// ------------------------------------------------------------------
// 库里的 Automator 在 autoFocus=true 时会监听 globalpointermove，
// 把指针位置换算成焦点喂给 FocusController（cubism4.js 里那个 automator）。
// 关掉之后焦点不会自己动，得手动拨回 (0,0)，否则眼珠会停在最后一次鼠标的位置。
function applyFollowMouse() {
  const automator = (model as unknown as { automator?: { autoFocus: boolean } } | null)?.automator
  if (automator) automator.autoFocus = props.followMouse

  if (!props.followMouse) {
    const focusController = (
      model?.internalModel as unknown as {
        focusController?: { focus(x: number, y: number, instant?: boolean): void }
      }
    )?.focusController
    focusController?.focus(0, 0, true)
  }
}

// 父组件切换 AI 控制模式时同步过来（模型还没加载完也没关系，加载完会再调一次）
watch(() => props.followMouse, applyFollowMouse)

// ------------------------------------------------------------------
// 组件挂载后：建舞台 + 加载模型
// ------------------------------------------------------------------
onMounted(async () => {
  // 两个 DOM 都拿到了才建舞台（TS 里它们可能是 null，必须先收窄）
  const canvas = canvasRef.value
  const stage = stageRef.value
  if (!canvas || !stage) return

  app = new PIXI.Application({
    view: canvas,
    backgroundAlpha: 0,          // 背景透明，下面那层海洋视频才能透上来
    antialias: true,             // 抗锯齿，线条边缘更顺滑
    autoDensity: true,           // canvas 的 CSS 尺寸自动跟进
    resolution: Math.min(window.devicePixelRatio || 1, 2),  // 高清屏更清晰，上限 2 防性能爆炸
    resizeTo: stage,             // 画布尺寸跟随这个容器
  })

  try {
    // 加载模型。注意：这一步依赖 index.html 里引入的 Cubism Core，
    // 如果 Core 没加载，会在这里抛错并被下面的 catch 接住
    // 0.5.0-beta 起推荐显式传 ticker（window.PIXI 那个 hack 已被标记为 deprecated）
    model = await Live2DModel.from(props.modelUrl, { ticker: PIXI.Ticker.shared })
    fixClippingMaskBuffer(model)   // 遮罩过多的模型必须先修，否则后面画不出来
    app.stage.addChild(model)
    layoutModel()
    applyFollowMouse()   // 建好就按当前设置决定眼睛跟不跟鼠标
    status.value = 'ready'

    // ===== 互动：点模型不同部位触发不同动作 =====
    // hitAreas 是模型作者定义的可点击区域，常见有 body / head
    // model.on('hit', (hitAreas) => {
    //   if (hitAreas.includes('body')) model.motion('tap_body')   // 戳身体
    //   if (hitAreas.includes('head')) model.motion('tap_head')   // 摸头
    // })
  } catch (err) {
    // catch 到的东西类型是 unknown，先判断一下再取 message
    const reason = err instanceof Error ? err.message : err
    console.warn('[Live2D] 模型还没准备好，显示占位框。原因：', reason)
    status.value = 'error'
  }

  // 容器尺寸变化时重算画布和模型位置
  resizeObserver = new ResizeObserver(() => {
    if (!app) return
    app.resize()
    layoutModel()
  })
  resizeObserver.observe(stage)
})

// ------------------------------------------------------------------
// 组件销毁：一定要清干净，否则来回切页面会内存泄漏
// ------------------------------------------------------------------
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  model?.destroy()
  app?.destroy(true, { children: true, texture: true, baseTexture: true })
  app = null
  model = null
})

// ------------------------------------------------------------------
// 暴露给外部的方法：以后让 AI 驱动小人就用这几个
// 父组件里先 <Live2DStage ref="live2dRef" />，再 live2dRef.value.xxx()
// ------------------------------------------------------------------
// Cubism 内核模型（pixi-live2d-display 没给完整类型，这里只声明用到的这个方法）
interface CubismCoreModel {
  setParameterValueById(id: string, value: number): void
}

// pixi-live2d-display 也没暴露 motionManager 的完整类型，这里只声明用到的部分。
// 为什么要碰它：库不允许重复启动「当前正在播的动作」，也不允许用相同优先级
// 打断正在播的动作，所以手动按钮要用 state + stopAllMotions 配合才能生效。
interface MotionManagerLike {
  state?: { currentGroup?: string; currentIndex?: number }
  stopAllMotions(): void
  expressionManager?: ExpressionManagerLike
}

// 表情管理器：setExpression 里有一条「和当前表情同名就直接 return false」的短路，
// 但我们切动作时会把表情复位掉，这时再挑同一个表情就什么都不会发生
// ——表现为「只有第一个表情生效，后面挑同一个就没反应」。所以这里把 currentExpression 清掉。
interface ExpressionManagerLike {
  resetExpression(): void
  currentExpression?: unknown
}

function getExpressionManager(): ExpressionManagerLike | undefined {
  return getMotionManager()?.expressionManager
}

function getMotionManager(): MotionManagerLike | undefined {
  return (model?.internalModel as unknown as { motionManager?: MotionManagerLike })
    ?.motionManager
}

// Cubism 的 coreModel 包装器（pixi-live2d-display 内部那一层）暴露的参数读写接口。
// 只声明我们复位参数用得到的方法。
interface CubismModelLike {
  getParameterCount(): number
  getParameterDefaultValue(index: number): number
  setParameterValueByIndex(index: number, value: number): void
}

function getCoreModel(): CubismModelLike | undefined {
  return (model?.internalModel as unknown as { coreModel?: CubismModelLike })?.coreModel
}

// ------------------------------------------------------------------
// resetAllParameters：把所有参数一键复位成模型默认值。
// 为什么需要：每个动作只驱动自己那几十个参数（摊手=手臂，变芒=变身形态…），
// 切换到别的动作时，上一个动作没被覆盖的参数会卡在最后一帧（因为它只被那个
// 动作写过，之后没人再动它），看起来就像"回不到待机/动作叠在一起"。
// 把全部参数拧回默认值，再播新动作，才能干净地切换。
// ------------------------------------------------------------------
function resetAllParameters() {
  const core = getCoreModel()
  if (!core) return
  const count = core.getParameterCount()
  for (let i = 0; i < count; i++) {
    core.setParameterValueByIndex(i, core.getParameterDefaultValue(i))
  }
}

// 动作优先级（对应库里的 MotionPriority）：IDLE=1 / NORMAL=2 / FORCE=3。
// 三个自定义动作（摊手/变芒/变荒）都是 NORMAL，而且都是循环播放；
// 库的规则是 priority <= currentPriority 就拒绝启动，于是「摊手」一开，
// 其他同为 NORMAL 的动作全被挡住。用 FORCE 才能互相打断。
const MOTION_PRIORITY_FORCE = 3

defineExpose({
  // 切表情：name 例如 '呆毛电风扇' / '哭'（模型里有哪些表情看 model3.json）
  setExpression(name: string) {
    const em = getExpressionManager()
    // 先清掉「当前表情」标记：库里 setExpression 发现跟当前表情同名会直接不播，
    // 而 resetToIdle 已经把表情复位了，这时挑回同一个表情就会静默失败
    if (em) em.currentExpression = undefined
    model?.expression(name)
  },
  // 播动作：group 例如 'Idle' / 'TapBody'，index 是第几个动作。
  // 每次点动作按钮都按「先停旧动作 → 参数复位 → 播新动作」来，
  // 否则旧动作会在下一帧继续写它自己的参数，把复位覆盖掉。
  playMotion(group: string, index = 0) {
    const mgr = getMotionManager()
    // 先停掉当前动作（同一动作连点、或切换到别的动作都要先停）
    mgr?.stopAllMotions()
    // 再把上一个动作残留的参数复位，避免手臂/变身形态卡住
    resetAllParameters()
    // 用 FORCE：允许从「摊手」直接切到「变芒」等任意动作，否则会被同优先级挡住
    model?.motion(group, index, MOTION_PRIORITY_FORCE)
  },
  // 回到待机：Idle 是「一直自动循环」的默认动画，直接 motion('Idle') 会被库
  // 当成「已经正在播」而拒绝。所以先强行停掉当前动作，再复位所有参数和表情，
  // 最后从第 0 帧重播待机，这样一定会回到中性待机状态。
  resetToIdle() {
    const mgr = getMotionManager()
    if (!mgr) return
    mgr.stopAllMotions()
    mgr.expressionManager?.resetExpression()
    resetAllParameters()
    model?.motion('Idle', 0)
  },
  // 口型：v 取值 0（闭嘴）~ 1（张大嘴）
  // 接了语音合成后，每帧根据音量算一个 v 传进来就能同步张嘴
  setMouthOpen(v: number) {
    // 库里把 coreModel 声明成了 object，调用前先断言成我们需要的最小接口
    const core = model?.internalModel?.coreModel as CubismCoreModel | undefined
    core?.setParameterValueById('ParamMouthOpenY', Math.min(1, Math.max(0, v)))
  },
})
</script>

<template>
  <div ref="stageRef" class="live2d-stage">
    <!-- 真正出画面的地方 -->
    <canvas ref="canvasRef" class="live2d-stage__canvas"></canvas>

    <!-- 模型不存在时显示的提示框：等你有模型了它会自动消失 -->
    <div v-if="status === 'error'" class="live2d-stage__empty">
      <p class="live2d-stage__title">这里以后站芙芙</p>
      <p class="live2d-stage__hint">
        把模型文件夹放进 <code>public/live2d/</code>，<br />
        再把 <code>modelUrl</code> 指到里面的 <code>.model3.json</code>
      </p>
    </div>
  </div>
</template>

<style scoped>
.live2d-stage {
  position: relative;   /* 占位提示要相对它绝对定位 */
  width: 100%;
  height: 100%;
  overflow: hidden;
}

/* canvas 铺满整个舞台 */
.live2d-stage__canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

/* ---- 没模型时的占位框 ---- */
.live2d-stage__empty {
  position: absolute;
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%);
  text-align: center;
  padding: 14px 22px;
  border: 2px dashed rgba(47, 62, 70, 0.35);
  border-radius: 14px;
  color: #2f3e46;
}
.live2d-stage__title {
  margin: 0 0 6px;
  font-size: 1.05rem;
  font-weight: 500;
}
.live2d-stage__hint {
  margin: 0;
  font-size: 0.85rem;
  color: #7b8a85;
  line-height: 1.6;
}
.live2d-stage__hint code {
  background: rgba(47, 62, 70, 0.08);
  padding: 1px 5px;
  border-radius: 4px;
}
</style>
