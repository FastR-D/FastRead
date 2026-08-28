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

  it('renders a grounded evidence matrix and structured feasibility claims', () => {
    expect(source).toContain('条已校验证据')
    expect(source).toContain('空缺会保留，不由模型补写')
    expect(source).toContain('SynthesisClaimList')
    expect(source).toContain('页码、逐字引文和论文成员关系由程序复核')
    expect(source).not.toContain('JSON.stringify(item)')
  })
})
