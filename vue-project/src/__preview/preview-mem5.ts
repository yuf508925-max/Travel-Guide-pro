import { createApp, h } from 'vue'
import ChatView from '../views/ChatView.vue'

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

;(async () => {
  await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'yufeng', password: '123456' }),
  })
  createApp({ render: () => h(ChatView, { username: 'yufeng', onLogout: () => {} }) }).mount('#app')
  await wait(3600)
  document.querySelector<HTMLButtonElement>('.mem-btn')?.click()
  await wait(2400)
  const nodes = [...document.querySelectorAll<SVGCircleElement>('.mem-node')]
  nodes[2]?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await wait(450)
})()