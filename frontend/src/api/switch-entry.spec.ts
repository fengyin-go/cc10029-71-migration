import { describe, expect, it } from 'vitest'

import { switchEntryLink } from './entry'

describe('switchEntryLink', () => {
  // 测试环境页面地址是 /portal/
  it('keeps the same record when returning to the legacy entry', () => {
    expect(switchEntryLink('/portal/review_meeting/3')).toBe('/review_meeting/3')
    expect(switchEntryLink('/portal/improve_task/4')).toBe('/improve_task/4')
    expect(switchEntryLink('/portal/receipts/M-56')).toBe('/receipts/M-56')
    expect(switchEntryLink('/portal/')).toBe('/')
  })

  it('preserves query and hash', () => {
    expect(switchEntryLink('/portal/review_meeting/3?receipt=M-56#row-3'))
      .toBe('/review_meeting/3?receipt=M-56#row-3')
  })
})
