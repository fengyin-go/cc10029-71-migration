import { describe, expect, it } from 'vitest'

describe('legacy entry api prefix', () => {
  it('uses /api when the page is at the root path', async () => {
    window.history.replaceState({}, '', '/review_meeting/3')
    const { apiPrefix, currentSite, isLegacyEntry } = await import('@/api/entry')
    expect(isLegacyEntry()).toBe(true)
    expect(currentSite()).toBe('legacy')
    expect(apiPrefix()).toBe('/api')
  })
})
