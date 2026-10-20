<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

const emit = defineEmits(['login'])

const form = ref({ username: '', password: '' })
const error = ref('')
const loading = ref(false)
// ===== 时钟 =====
const now = ref(new Date())
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => { timer = setInterval(() => (now.value = new Date()), 1000) })
onBeforeUnmount(() => clearInterval(timer))

const pad = (n: number) => String(n).padStart(2, '0')
const hh = computed(() => pad(now.value.getHours()))
const mm = computed(() => pad(now.value.getMinutes()))
const ss = computed(() => pad(now.value.getSeconds()))
const dateStr = computed(() =>
  `${now.value.getFullYear()}/${now.value.getMonth() + 1}/${now.value.getDate()} ` +
  now.value.toLocaleDateString('zh-CN', { weekday: 'long' }))



const handleSubmit = () => {
  error.value = ''
  if (!form.value.username.trim() || !form.value.password.trim()) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  // 现在是假登录，将来换成真实接口：await fetch('/api/login', ...)
  setTimeout(() => {
    loading.value = false
    emit('login', form.value.username.trim())
  }, 600)
}
</script>

<!-- src="/studio_video_1716732543213.gif" width="1200" height="920" -->

<template>
  <div class="login-page">

    <!-- 黄色：视频区 -->
    <figure class="login-pic">
      <div class="login-pic-inner">
        <!-- <video
          class="login-video"
          src="/studio_video_1716732543213.mp4"
          poster="/45-4544.png"
          autoplay
          muted
          loop
          playsinline
          preload="auto">
        </video> -->
        <video
          class="login-video"
          src="/studio_video_1716732543213.mp4"
          poster="/45-4544.png"
          autoplay muted loop playsinline preload="auto"
          disablepictureinpicture
          controlslist="nodownload noplaybackrate nofullscreen">
        </video>


        <!-- ↓ 新增这一行，必须写在 video 的后面 -->
        <div class="login-pic-overlay">旅行指南 · 与芙同行</div>
      </div>
    </figure>

    <!-- 右列 -->
    <div class="login-side">

      <!-- 时钟：放在右列最上面 -->
      <div class="login-clock">
        <div class="login-clock__time">
          {{ hh }}<span class="login-clock__colon">:</span>{{ mm }}<span class="login-clock__sec">{{ ss }}</span>
        </div>
        <div class="login-clock__date">{{ dateStr }}</div>
      </div>

      <!-- 绿色：头像 + 标题组合 -->
      <div class="login-brand">
        <img class="login-avatar" src="/1790414746809.png" alt="芙芙头像" />
        <div>
          <h1 class="login-name">旅行指南</h1>
          <p class="login-desc">登录后即可和芙芙开启你的旅途</p>
        </div>
      </div>

      <!-- 红色：登录框 -->
      <div class="login-panel">
        <div class="login-card">
          <form class="login-form" @submit.prevent="handleSubmit">
            <div class="form-item">
              <label class="form-label" for="username">用户名：</label>
              <input id="username" class="form-input" v-model="form.username" type="text" placeholder="请输入用户名" />
            </div>
            <div class="form-item">
              <label class="form-label" for="password">密码：</label>
              <input id="password" class="form-input" v-model="form.password" type="password" placeholder="请输入密码" />
            </div>
            <p v-if="error" class="form-error">{{ error }}</p>
            <button class="login-btn" type="submit" :disabled="loading">
              {{ loading ? '登录中…' : '登录' }}
            </button>
          </form>
        </div>
      </div>

    </div>
  </div>
</template>


<style scoped>
.login-page {
  min-height: 100vh;
  box-sizing: border-box;
  display: flex;
  align-items: stretch;      /* 左右两列等高，图片才能撑满 */
  gap: 40px;
  padding: 36px;
  /* background: #f4f1ea; */
}

/* ===== 黄色：大图区 ===== */
.login-pic {
  margin: 0;
  flex: 1 1 auto;            /* 吃掉右侧剩下的全部宽度 */
  min-width: 0;
  padding: 28px;             /* 边界 ↔ 线条 */
  box-sizing: border-box;
}

.login-pic-inner {
  position: relative;
  height: 100%;
  box-sizing: border-box;
  padding: 14px;             /* 线条 ↔ 图片 */
  border: 2px solid #2f3e46;
  border-radius: 16px;
  background: #fffdf8;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06);
}

/* ↓ 在 .login-pic video 那段后面，新增这一整块 */
.login-pic-overlay {
  position: absolute;
  left: 24px;
  bottom: 24px;
  color: #ffffff;
  font-size: 1.5rem;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
}


.login-pic img,
.login-pic video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;        /* 视频自动裁剪填满画框，不变形 */
  border-radius: 8px;
}


/* .login-pic img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;         图片自动裁剪填满整个画框
  border-radius: 8px;
} */

/* ===== 时钟 ===== */
.login-clock {
  text-align: center;
  margin-bottom: 28px;
  color: #7fe7ff;
  text-shadow: 0 0 12px rgba(94, 220, 255, 0.8), 0 0 30px rgba(94, 220, 255, 0.4);
}

.login-clock__time {
  font-size: 3.4rem;
  font-weight: 500;
  line-height: 1;
  font-variant-numeric: tabular-nums;  /* 数字等宽，秒跳动时不会左右晃 */
}

.login-clock__colon { margin: 0 0.1rem; opacity: 0.7; }

.login-clock__sec { font-size: 1.4rem; margin-left: 0.3rem; opacity: 0.85; }

.login-clock__date { font-size: 0.95rem; margin-top: 8px; opacity: 0.9; }


/* ===== 右列：绿区 + 红区 垂直排列 ===== */
.login-side {
  flex: 0 0 420px;
  display: flex;
  flex-direction: column;
  justify-content: center;   /* 绿+红整体垂直居中 */
}

/* ===== 绿色：头像 + 标题 ===== */
.login-brand {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 28px;
  padding: 0 8px;
}

.login-avatar {
  flex: 0 0 auto;
  width: 76px;
  height: 76px;
  border-radius: 50%;        /* 圆形头像 */
  object-fit: cover;
  border: 3px solid #fffdf8; /* 白色描边，参考图那种效果 */
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
}

.login-name {
  margin: 0 0 6px;
  font-size: 1.7rem;
  font-weight: 500;
  color: #2f3e46;
}

.login-desc {
  margin: 0;
  font-size: 0.95rem;
  color: #7b8a85;
}

/* ===== 红色：登录画框 ===== */
.login-panel {
  padding: 28px;
  box-sizing: border-box;
}

.login-card {
  padding: 28px;
  border: 2px solid #2f3e46;
  border-radius: 16px;
  background: #fffdf8;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06);
}

/* ===== 表单 ===== */
.form-item { display: flex; flex-direction: column; gap: 6px; margin-bottom: 18px; }
.form-label { font-size: 0.9rem; color: #55635f; }

.form-input {
  box-sizing: border-box;
  height: 46px;
  padding: 0 14px;
  font-size: 1rem;
  color: #2f3e46;
  border: 1px solid #c9d2cd;
  border-radius: 8px;
  outline: none;
  transition: border-color 0.2s;
}
.form-input:focus { border-color: #2f7d6e; }

.form-error { margin: 0 0 12px; font-size: 0.85rem; color: #c0392b; }

.login-btn {
  width: 100%;
  height: 48px;
  border: none;
  border-radius: 8px;
  background: #2f7d6e;
  color: #fff;
  font-size: 1.05rem;
  cursor: pointer;
  transition: background 0.2s;
}
.login-btn:hover:not(:disabled) { background: #256354; }
.login-btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* ===== 窄屏：上下排列 ===== */
@media (max-width: 1024px) {
  .login-page { flex-direction: column; gap: 32px; padding: 24px; }
  .login-side { flex: 0 0 auto; width: 100%; max-width: 440px; margin: 0 auto; }
  .login-pic { width: 100%; min-height: 320px; }
}

</style>
