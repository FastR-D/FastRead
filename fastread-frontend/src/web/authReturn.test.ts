import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { arrivalParameters, clearCASDestination, rememberCASDestination } from './authReturn'

let values: Map<string, string>
beforeEach(() => {
  values = new Map()
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => values.get(key) || null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  })
  vi.stubGlobal('window', {
    location: { search: '?paper=paper-1&section=settings&auth=cas&redirect=https://other.test' },
  })
})
afterEach(() => vi.unstubAllGlobals())

describe('CAS entry restoration', () => {
  it('restores only application parameters after a successful callback', () => {
    rememberCASDestination()
    window.location.search = '?fastcas=complete'
    const query = arrivalParameters()
    expect(query.get('paper')).toBe('paper-1')
    expect(query.get('section')).toBe('settings')
    expect(query.has('auth')).toBe(false)
    expect(query.has('redirect')).toBe(false)
    clearCASDestination()
    expect(arrivalParameters().has('paper')).toBe(false)
  })
  it('does not override an explicit destination or restore a failed login', () => {
    rememberCASDestination()
    window.location.search = '?fastcas=failed'
    expect(arrivalParameters().has('paper')).toBe(false)
    window.location.search = '?fastcas=complete&paper=explicit'
    expect(arrivalParameters().get('paper')).toBe('explicit')
  })
  it('ignores expired and malformed tab state', () => {
    values.set(
      'fastread.cas.destination',
      JSON.stringify({ created: Date.now() - 600_001, parameters: { paper: 'old' } })
    )
    window.location.search = '?fastcas=complete'
    expect(arrivalParameters().has('paper')).toBe(false)
    values.set('fastread.cas.destination', 'broken')
    expect(arrivalParameters().has('paper')).toBe(false)
  })
})
