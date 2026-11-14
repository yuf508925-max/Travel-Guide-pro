// =====================================================================
// useLipSync.ts —— 把正在播放的 TTS 语音变成 Live2D 的嘴型
// ---------------------------------------------------------------------
// 思路很朴素：TTS 的音频本来就是"这句话长什么样"，不用再识别一遍。
// 用 Web Audio 把 <audio> 里的波形接出来，每帧算一次音量（RMS），
// 音量越大嘴张得越大，再往 ParamMouthOpenY 上一怼，口型就跟上了。
//
// 注意两件事：
//   1. createMediaElementSource 一个 <audio> 只能调一次，所以记住绑过的元素；
//   2. 音源必须接到 destination，否则只有分析没有声音（等于静音）。
//
// 只用音量驱动，所以只对得上"张嘴/闭嘴"的节奏，对不上具体音节——
// 这刚好是 Live2D 普通嘴型参数能做到的程度，再细就得靠 viseme 了。
// =====================================================================

import { onBeforeUnmount } from 'vue'

/** 音量 → 开口度的放大倍数 */
const GAIN = 6.5
/** 低于这个 RMS 当成环境噪声，嘴闭着 */
const GATE = 0.012
/** 张嘴比闭嘴快一点，看起来才像在说话 */
const ATTACK = 0.6
const RELEASE = 0.2

export function useLipSync(setMouth: (value: number) => void) {
  let ctx: AudioContext | null = null
  let analyser: AnalyserNode | null = null
  let data: Uint8Array<ArrayBuffer> | null = null
  let source: MediaElementAudioSourceNode | null = null
  /** 已经接过分析器的 <audio>，同一个元素不能重复 createMediaElementSource */
  let bound: HTMLAudioElement | null = null

  let raf = 0
  let level = 0
  let active = false
  let fallbackTimer = 0

  function ensureContext(): boolean {
    if (ctx) return true
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!Ctor) return false
    try {
      ctx = new Ctor()
      analyser = ctx.createAnalyser()
      // 只要音量包络，1024 点足够，再多就是浪费
      analyser.fftSize = 1024
      analyser.smoothingTimeConstant = 0.2
      data = new Uint8Array(analyser.fftSize)
      analyser.connect(ctx.destination)
      return true
    } catch {
      ctx = null
      return false
    }
  }

  function bind(el: HTMLAudioElement): boolean {
    if (bound === el) return true
    if (!ensureContext() || !ctx || !analyser) return false
    try {
      source?.disconnect()
      source = ctx.createMediaElementSource(el)
      source.connect(analyser)
      bound = el
      return true
    } catch {
      // 元素已经被接过一次（比如浏览器里还有别的实例），只能放弃这次口型
      return false
    }
  }

  function clearTimers() {
    if (raf) {
      cancelAnimationFrame(raf)
      raf = 0
    }
    if (fallbackTimer) {
      clearTimeout(fallbackTimer)
      fallbackTimer = 0
    }
  }

  function stop() {
    active = false
    clearTimers()
    bound?.removeEventListener('ended', stop)
    bound?.removeEventListener('pause', stop)
    level = 0
    setMouth(0)
  }

  function tick() {
    if (!active || !analyser || !data) {
      raf = 0
      return
    }
    analyser.getByteTimeDomainData(data)
    let sum = 0
    for (let i = 0; i < data.length; i += 1) {
      const v = ((data[i] ?? 128) - 128) / 128
      sum += v * v
    }
    const rms = Math.sqrt(sum / data.length)
    const target = rms > GATE ? Math.min(1, Math.pow(rms * GAIN, 0.75)) : 0
    const k = target > level ? ATTACK : RELEASE
    level += (target - level) * k
    if (level < 0.008) level = 0
    setMouth(level)
    raf = requestAnimationFrame(tick)
  }

  /**
   * 开始跟一段正在播放的语音。
   * @param el        PhoneCall 里那个 <audio>
   * @param durationMs 兜底时长：万一拿不到 ended 事件，到点也得闭嘴
   */
  function start(el: HTMLAudioElement | null, durationMs = 0) {
    if (!el) return
    if (!bind(el)) return
    stop()
    active = true
    level = 0
    void ctx?.resume().catch(() => {})
    el.addEventListener('ended', stop)
    el.addEventListener('pause', stop)
    if (durationMs > 0) fallbackTimer = window.setTimeout(stop, durationMs + 800)
    raf = requestAnimationFrame(tick)
  }

  onBeforeUnmount(() => {
    stop()
    source?.disconnect()
    source = null
    void ctx?.close().catch(() => {})
    ctx = null
    analyser = null
    data = null
    bound = null
  })

  return { start, stop }
}
