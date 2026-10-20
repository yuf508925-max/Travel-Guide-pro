# Travel Guide pro · 项目约定

## 技术栈

- Vue 3 + Vite + TypeScript，`vue-tsc --build` 做类型检查（package.json 的 `type-check`）
- **包管理器用 pnpm（项目根有 pnpm-lock.yaml）**。Windows 上 `npm install` 会因 `EPERM: symlink` 失败
  （npm 用真符号链接需管理员；pnpm 用 junction 不需要）。缺依赖时执行 `pnpm install`。
- Live2D：`pixi.js@^7.4.3` + `pixi-live2d-display@0.5.0-beta`
  - 注意：**不要**升到 pixi 8（0.5.0-beta 只兼容 pixi 7；pixi 8 要用 `@jannchie/pixi-live2d-display`）
  - Cubism Core 由 `index.html` 引 CDN：`https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js`（当前是 Core 5.1）

## 约定

- 所有 `.vue` 的 script 一律写 `<script setup lang="ts">`。
  没有 `lang="ts"` 的组件，在 TS 文件里 import 会报 `TS7016: Could not find a declaration file for module 'xxx.vue'`。
- 模型放在 `public/芙宁娜（vts）/`（中文+全角括号路径实测可用，浏览器会自动百分号编码），
  组件默认 `modelUrl = '/live2d/index.model3.json'`，ChatView 里显式传 `model-url`。
- 模型 `model3.json` 已手工补过 `Motions` / `Expressions` / `Groups.EyeBlink`，原文件备份为同目录 `.bak`。
- BGM：`public/Travelers' encore - Andrew Prahlow.mp3`，在 ChatView 顶部隐藏 `<audio>` 里播放，
  由导航条右侧的音量键（喇叭按钮 + range 滑块，默认 80）控制。
- 打包产物大：模型 118MB，`vite build` 会把 public 整拷进 dist；后续可考虑 CDN / 异步加载。

## 已知坑（详见 .workbuddy/memory/2026-10-03.md）

1. 遮罩 >36 的模型必须在 `Live2DStage.vue` 的 `fixClippingMaskBuffer()` 里重算遮罩纹理数量，否则渲染抛异常、画面空白。
2. 算缩放不能用 `model.width/height`（含当前 scale，会震荡），要用 `model.internalModel.getSize()`。
