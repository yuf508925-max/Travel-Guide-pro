// =====================================================================
// types/vlog.ts —— 「观看 vlog」用到的数据类型
//   后端 server/bilibili.py 解析出来的字段，直接照着写，
//   两个组件（列表卡片 / 浮窗播放器）共用这一份。
// =====================================================================

export interface VlogVideo {
  /** B 站视频号，如 BV1L5466gEKP */
  bvid: string
  title: string
  /** 封面，已补成 https:// 开头 */
  cover: string
  /** UP 主名字 */
  author: string
  /** UP 主头像 */
  author_avatar: string
  play: number
  danmaku: number
  /** "12:34" 这种时长 */
  duration: string
  pubdate: number
  description: string
  /** 原页面地址 */
  url: string
}
