import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./RelatedWorkView.tsx', import.meta.url), 'utf8')

describe('related work product boundary', () => {
  it('renders anchors, relevance, provenance, provider degradation, and empty state', () => {
    expect(source).toContain('检索锚点')
    expect(source).toContain('相关度')
    expect(source).toContain('元数据：')
    expect(source).toContain('provider_status')
    expect(source).toContain('这不表示本文没有相关工作')
  })

  it('distinguishes connected zero results, missing configuration, and real failures', () => {
    expect(source).toContain("status.via_proxy ? '代理已连接' : '已连接'")
    expect(source).toContain('· 暂无匹配')
    expect(source).toContain('手动检索已启用 · 自动聚合需 API')
    expect(source).toContain('暂时连接失败 · 可重试')
    expect(source).toContain('连接超时 · 可重试')
    expect(source).toContain('代理已连接 · 来源限流')
  })

  it('paginates a large result pool and lets the reader change page size', () => {
    expect(source).toContain('const pageSizeOptions = [10, 20, 50, 100]')
    expect(source).toContain('aria-label="每页近邻数量"')
    expect(source).toContain('aria-label="上一页近邻"')
    expect(source).toContain('aria-label="下一页近邻"')
    expect(source).toContain('visibleNeighbors.map')
    expect(source).toContain('limit: 120')
  })

  it('makes keyword, arXiv, and Elasticsearch priority visible', () => {
    expect(source).toContain('关键词检索')
    expect(source).toContain('主通道 · arXiv')
    expect(source).toContain('主通道 · Elasticsearch')
    expect(source).toContain('补充来源')
    expect(source).toContain('结果池：')
  })

  it('translates the active backend and offers manual Scholar search', () => {
    expect(source).toContain("value === 'local_inverted_index'")
    expect(source).toContain('当前使用：{backendLabel(snapshot.search_backend)}')
    expect(source).toContain('未启用 · 已自动使用本地索引')
    expect(source).toContain('通过系统代理在 Scholar 手动搜索当前锚点')
  })

  it('renders local bibliography provenance without an invalid retrieval date', () => {
    expect(source).toContain("replace('paper_bibliography', '本文参考文献')")
    expect(source).toContain('来源：本文第 {neighbor.provenance.source_page} 页引文')
    expect(source).toContain('hasRetrievedAt')
    expect(source).not.toContain('new Date(neighbor.provenance.retrieved_at).toLocaleString')
  })

  it('discloses proxy-only external search and the local Elasticsearch boundary', () => {
    expect(source).toContain('需要代理 · 当前未连接')
    expect(source).toContain('外部学术来源默认通过代理访问')
    expect(source).toContain('不会静默直连')
    expect(source).toContain('Elasticsearch 连接由用户配置的本机或局域网实例')
    expect(source).toContain('查看组合检索式')
  })

  it('states that discovery is not truth adjudication', () => {
    expect(source).toContain('不判断任何论文主张为真、假、支持或反驳')
    expect(source).not.toContain('置信度')
    expect(source).not.toContain('信源等级')
  })

  it('adds an explicit model-ranked layer without hiding the complete keyword pool', () => {
    expect(source).toContain('data-testid="smart-neighbor-section"')
    expect(source).toContain('AI 智能精选')
    expect(source).toContain('封闭候选池')
    expect(source).toContain('全部关键词近邻')
    expect(source).toContain('AI 精选不会删除或遮蔽这些论文')
    expect(source).toContain('candidate_count')
    expect(source).toContain('failure_reason')
    expect(source).toContain('候选全文导入前仍属于发现判断')
    expect(source).toContain('不要求模型凑满名额')
    expect(source).toContain('代码门槛 ≥')
  })

  it('polls an asynchronous cached selection job and exposes model control', () => {
    expect(source).toContain('getSmartNeighborSelection')
    expect(source).toContain('startSmartNeighborSelection')
    expect(source).toContain('aria-label="智能精选模型"')
    expect(source).toContain('后台正在比较')
    expect(source).toContain('重新精选')
  })
})
