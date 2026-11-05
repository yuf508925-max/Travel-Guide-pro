<!-- ====================================================================
  BubbleText —— "冒泡输出"的文字渲染器
  职责只有一个：把一段文字拆成一个个"小泡泡"，每个字自己蹦出来。
  为什么单独抽一个组件？
    MessageList.vue 只管气泡长什么样（底色、圆角、左右对齐），
    "字怎么冒出来"这件事全放在这里，以后想换动画（打字机、溶解、彩虹）
    只改这一个文件，聊天界面一行都不用动。
  用法：<BubbleText :text="msg.text" />  文字变长时，新字会自动冒出来
==================================================================== -->

<script setup lang="ts">
import { computed } from 'vue'
import type { CSSProperties } from 'vue'

const props = withDefaults(
  defineProps<{
    text?: string
    // 关掉后整段文字直接显示、不做逐个冒泡（打印 / 不想动效时用）
    animated?: boolean
  }>(),
  { text: '', animated: true }
)

// 一个"冒泡单元"：要么是一个汉字/符号，要么是一整个英文单词
interface Chunk {
  key: number     // 稳定 key：只有新字会新建节点，老字不会重播动画
  value: string   // 真正要显示的内容
  bubble: boolean // 是否要单独冒泡（空格 / 换行这种不冒）
  order: number   // 第几个冒泡：用来算 animation-delay
}

// 让长文本的入队延迟封顶：最多前 28 个单元排队，
// 否则模型一口气吐 300 字时，最后一个字要等好几秒才露头。
const MAX_ORDER = 28
// 超长英文单词（比如一长串网址）强制按字切开，不然 inline-block 不让折行会撑破气泡
const MAX_WORD = 16

const chunks = computed<Chunk[]>(() => {
  const src = props.text ?? ''
  const out: Chunk[] = []
  let i = 0
  let order = 0

  // 往结果里塞一个单元（纯文本单元不占延迟名额）
  const push = (value: string, bubble: boolean) => {
    out.push({
      key: out.length,
      value,
      bubble,
      order: bubble ? Math.min(order++, MAX_ORDER) : 0,
    })
  }

  while (i < src.length) {
    const ch = src.charAt(i)

    // 1) 空白（空格 / 换行 / 制表符）：原样输出成纯文本。
    //    空白绝不能包成 inline-block，否则折行位置会跑偏，
    //    复制出来的文字也会多出空格。
    if (/\s/.test(ch)) {
      let j = i
      while (j < src.length && /\s/.test(src.charAt(j))) j++
      push(src.slice(i, j), false)
      i = j
      continue
    }

    // 2) 英文 / 数字：整词一起冒。
    //    逐个字母包成 inline-block 的话，浏览器会把单词当独立块，
    //    可能从中间断行（"trav el"），所以按单词切。
    if (/[A-Za-z0-9]/.test(ch)) {
      let j = i
      while (j < src.length) {
        const c = src.charAt(j)
        const isWordChar = /[A-Za-z0-9'’\-_]/.test(c)
        // 句点只有夹在字母中间（v1.2 / e.g）才算单词的一部分
        const isInnerDot = c === '.' && /[A-Za-z0-9]/.test(src.charAt(j + 1))
        if (!isWordChar && !isInnerDot) break
        j++
      }
      const word = src.slice(i, j)
      if (word.length > MAX_WORD) {
        // 太长 → 退化成逐字，保证能折行
        for (const c of word) push(c, true)
      } else {
        push(word, true)
      }
      i = j
      continue
    }

    // 3) 中文 / 标点 / emoji：一个字一个泡泡，节奏最密
    push(ch, true)
    i++
  }

  return out
})

// 把"第几个冒"写成 CSS 变量，延迟交给动画自己算
function unitStyle(order: number): CSSProperties {
  return { '--bubble-order': order } as CSSProperties
}
</script>

<template>
  <span class="bubble-text" :class="{ 'bubble-text--static': !animated }">
    <span
      v-for="c in chunks"
      :key="c.key"
      class="bubble-text__unit"
      :class="{ 'bubble-text__unit--char': c.bubble }"
      :style="c.bubble ? unitStyle(c.order) : undefined"
      >{{ c.value }}</span
    >
  </span>
</template>

<style scoped>
/* 保留原来的换行和连续空格（气泡里的 white-space: pre-wrap 靠它继承） */
.bubble-text {
  white-space: pre-wrap;
}

/* ---- 会冒的那个字 ---- */
.bubble-text__unit--char {
  display: inline-block;          /* 只有变成块才能独立做 transform */
  transform-origin: 50% 100%;     /* 从字底往上弹，像水泡浮起来 */
  animation: bubble-char 0.42s cubic-bezier(0.34, 1.56, 0.64, 1) both;
  animation-delay: calc(var(--bubble-order, 0) * 18ms);
}

/* 从"水下"升起：小、透明、带一点模糊 → 归位 */
@keyframes bubble-char {
  0% {
    opacity: 0;
    transform: translateY(0.45em) scale(0.55);
    filter: blur(2px);
  }
  55% {
    opacity: 1;
    transform: translateY(-0.08em) scale(1.06);   /* 略微过冲，弹一下 */
    filter: blur(0);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
    filter: blur(0);
  }
}

/* 直接显示（不做逐个冒泡） */
.bubble-text--static .bubble-text__unit--char {
  display: inline;
  animation: none;
}

/* 系统开了"减少动态效果"就老实点，别让人晕 */
@media (prefers-reduced-motion: reduce) {
  .bubble-text__unit--char {
    animation: none;
  }
}
</style>
