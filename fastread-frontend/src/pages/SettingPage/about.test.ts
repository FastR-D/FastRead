import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const aboutSource = readFileSync(new URL('./about.tsx', import.meta.url), 'utf8')

describe('FastRead about page copy', () => {
  it('describes the page-aware paper-reading workflow', () => {
    for (const requiredCopy of [
      '论文原文',
      '分页原文',
      '可追溯引用',
      '300 字个人总结',
      '带页码持续追问',
    ]) {
      expect(aboutSource).toContain(requiredCopy)
    }
  })

  it('does not reintroduce the retired video-product positioning', () => {
    const retiredCopy = [
      ['Reel', 'Mind'].join(''),
      ['抖', '音'].join(''),
      ['短', '视频'].join(''),
      ['视频', '笔记'].join(''),
      ['M', 'V', 'P'].join(''),
    ]
    for (const copy of retiredCopy) {
      expect(aboutSource).not.toContain(copy)
    }
  })
})
