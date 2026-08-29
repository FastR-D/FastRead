import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./ResearchPage.tsx', import.meta.url), 'utf8')

describe('research topic synthesis experience', () => {
  it('lets the user select the model used for topic summaries and questions', () => {
    expect(source).toContain('aria-label="专题知识库使用模型"')
    expect(source).toContain('onModelChange(event.target.value)')
    expect(source).toContain('String(item.id) === selectedModelId')
    expect(source).toContain('provider_id: model.provider_id')
    expect(source).toContain('model_name: model.model_name')
  })

  it('keeps evidence preparation internal and prioritizes grounded synthesis', () => {
    expect(source).not.toContain('证据矩阵')
    expect(source).not.toContain('手工补充逐字证据')
    expect(source).not.toContain('智能补全矩阵')
    expect(source).toContain('不再要求你维护单独的证据条目')
    expect(source).toContain('extractTopicEvidence')
    expect(source).toContain('SynthesisClaimList')
    expect(source).toContain('页码、逐字引文和论文成员关系由程序复核')
    expect(source).not.toContain('JSON.stringify(item)')
    expect(source.indexOf('{synthesis && <SynthesisView')).toBeLessThan(source.indexOf('<KnowledgeBaseChat'))
  })

  it('restores the selected topic and latest persisted synthesis after refresh', () => {
    expect(source).toContain('listTopicSyntheses(id)')
    expect(source).toContain('setSynthesis(syntheses[0] || null)')
    expect(source).toContain('fastread-selected-research-topic')
    expect(source).toContain('window.localStorage.getItem(SELECTED_TOPIC_STORAGE_KEY)')
  })
})
