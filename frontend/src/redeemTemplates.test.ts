import { describe, expect, it } from 'vitest'
import { templateRedemption } from './redeemTemplates'

describe('快速扣點商品', () => {
  it('套用商品名稱、半點價格與模板 ID，不修改原模板', () => {
    const item = { id: 'coffee', name: '咖啡', points: 50.5 }
    expect(templateRedemption(item)).toEqual({ amount: 50.5, reason: '商品：咖啡', redeem_template_id: 'coffee' })
    expect(item).toEqual({ id: 'coffee', name: '咖啡', points: 50.5 })
  })
  it('拒絕不是半點倍數的價格', () => {
    expect(() => templateRedemption({ id: 'coffee', name: '咖啡', points: 0.25 })).toThrow()
  })
})
