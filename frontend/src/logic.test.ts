import { describe, expect, it } from 'vitest'
import { parseToken, points, taipei, requestId } from './logic'
describe('掃碼與點數驗證', () => {
  it('在沒有 randomUUID 的 HTTP 環境產生不重複 UUID v4', () => {
    const ids = Array.from({ length: 1000 }, () => requestId())
    expect(new Set(ids).size).toBe(1000)
    expect(ids.every(id => /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id))).toBe(true)
  })
  it('接受 HID Enter 結尾，拒絕網址及腳本', () => {
    expect(parseToken('a'.repeat(43) + '\r\n')).toBe('a'.repeat(43))
    for (const value of ['https://example.org', '<script>', '', 'a'.repeat(44)]) expect(() => parseToken(value)).toThrow()
  })
  it('拒絕零、負數、小數與不安全整數', () => {
    for (const value of [0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1, NaN]) expect(() => points(value)).toThrow()
    expect(points(0, true)).toBe(0)
    expect(points(500)).toBe(500)
  })
  it('固定使用台北時間', () => { expect(taipei('2026-01-01T00:00:00Z')).toContain('08:00:00') })
})
