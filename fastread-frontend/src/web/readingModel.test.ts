import { describe, expect, it } from 'vitest'
import {
  evaluateExpression,
  experimentDifference,
  readingItemText,
  repositorySourceURL,
  type Expression,
} from './readingModel'

describe('declarative reading calculations', () => {
  it('recalculates a formula with changed inputs', () => {
    const expression: Expression = { op: 'div', args: [{ op: 'mul', args: ['x', 'x'] }, 'scale'] }
    expect(evaluateExpression(expression, { x: 4, scale: 2 })).toBe(8)
    expect(evaluateExpression(expression, { x: 6, scale: 2 })).toBe(18)
  })
  it('rejects unknown operations, variables and invalid domains', () => {
    expect(() => evaluateExpression({ op: 'eval', args: ['alert(1)'] }, {})).toThrow()
    expect(() => evaluateExpression('constructor', {})).toThrow()
    expect(() => evaluateExpression({ op: 'div', args: [1, 0] }, {})).toThrow(/定义域/)
    expect(() => evaluateExpression({ op: 'sqrt', args: [-1] }, {})).toThrow()
    expect(() => evaluateExpression({ op: 'add', args: [1] }, {})).toThrow()
    expect(() => evaluateExpression('x', { x: NaN })).toThrow()
  })
  it('bounds recursion and does not evaluate javascript strings', () => {
    let expression: Expression = 1
    for (let i = 0; i < 20; i++) expression = { op: 'neg', args: [expression] }
    expect(() => evaluateExpression(expression, {})).toThrow(/复杂/)
    expect(() => evaluateExpression('globalThis.location.href', {})).toThrow()
  })
  it('keeps missing experiment values distinct from zero', () => {
    expect(experimentDifference('', '0')).toBeNull()
    expect(experimentDifference('unreported', '3')).toBeNull()
    expect(experimentDifference('0', '3')).toBe(-3)
    expect(experimentDifference('95.5', '90')).toBe(5.5)
  })
  it('retains literal evidence and page in note excerpts', () => {
    expect(
      readingItemText({
        step: 'Encode',
        description: 'Encode tokens.',
        evidence: [{ page: 3, exact_quote: 'Original source text.' }],
      })
    ).toContain('> 第 3 页：Original source text.')
  })
})

describe('repository source links', () => {
  it('links only fixed commits and valid line ranges', () => {
    const repo = {
      url: 'https://github.com/owner/repo',
      commit: 'a'.repeat(40),
      paths: ['src/model.py'],
    }
    expect(repositorySourceURL(repo, 'src/model.py', 2, 8)).toBe(
      `${repo.url}/blob/${repo.commit}/src/model.py#L2-L8`
    )
    expect(
      repositorySourceURL({ ...repo, url: 'javascript:alert(1)' }, 'src/model.py', 1, 2)
    ).toBeUndefined()
    expect(repositorySourceURL({ ...repo, commit: 'main' }, 'src/model.py', 1, 2)).toBeUndefined()
    expect(repositorySourceURL(repo, '../model.py', 1, 2)).toBeUndefined()
    expect(repositorySourceURL(repo, 'src/model.py', 8, 2)).toBeUndefined()
  })
})
