import { describe, expect, it } from 'vitest'
import { paperImportModelFields } from './paperImport'

describe('paperImportModelFields', () => {
  it('allows paper import before a model is configured', () => {
    expect(paperImportModelFields(null)).toEqual({
      provider_id: '',
      model_name: '',
    })
  })

  it('keeps a complete configured model for later report generation', () => {
    expect(paperImportModelFields({
      provider_id: ' provider-1 ',
      model_name: ' qwen-plus ',
    })).toEqual({
      provider_id: 'provider-1',
      model_name: 'qwen-plus',
    })
  })

  it('does not persist a partial model selection', () => {
    expect(paperImportModelFields({ provider_id: 'provider-1' })).toEqual({
      provider_id: '',
      model_name: '',
    })
  })
})
