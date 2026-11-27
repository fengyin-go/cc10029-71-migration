import { describe, expect, it } from 'vitest'

import {
  apiPrefix,
  isLegacyEntry,
  isPortalPath,
  portalBase,
  portalRoot,
  siteLink,
  stripPortalPrefix,
} from './entry'

describe('entry base helpers', () => {
  it('exposes the portal prefix', () => {
    expect(portalRoot()).toBe('/portal')
    expect(portalBase()).toBe('/portal/')
  })

  it('detects legacy entry paths', () => {
    expect(isLegacyEntry('/review_meeting/3')).toBe(true)
    expect(isLegacyEntry('/')).toBe(true)
    expect(isLegacyEntry('/portal/')).toBe(false)
    expect(isLegacyEntry('/portal/review_meeting/3')).toBe(false)
  })

  it('picks the API prefix per live entry', () => {
    // happy-dom 的测试地址是门户入口。
    expect(apiPrefix()).toBe('/portal/api')
    expect(isLegacyEntry('/portal/overview')).toBe(false)
  })

  it('strips the portal prefix back to business paths', () => {
    expect(stripPortalPrefix('/portal/review_meeting/3')).toBe('/review_meeting/3')
    expect(stripPortalPrefix('/review_meeting/3')).toBe('/review_meeting/3')
    expect(stripPortalPrefix('/portal/')).toBe('/')
    expect(isPortalPath('/portal/receipts/M-56')).toBe(true)
    expect(isPortalPath('/receipts/M-56')).toBe(false)
  })

  it('keeps in-site links inside the current entry', () => {
    expect(siteLink('/review_meeting')).toBe('/portal/review_meeting')
    expect(siteLink('/')).toBe('/portal')
  })
})
