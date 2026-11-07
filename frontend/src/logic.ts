export const MAX = 9007199254740991
// getRandomValues is available on isolated LAN HTTP; randomUUID requires HTTPS/localhost.
export function requestId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 15) | 64
  bytes[8] = (bytes[8] & 63) | 128
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
export function parseToken(value: string): string {
  const token = value.trim()
  if (!/^[A-Za-z0-9_-]{43}$/.test(token)) throw new Error('請掃描有效的 QR Token；不接受網址')
  return token
}
export function points(value: number, zero = false): number {
  if (!Number.isSafeInteger(value) || value < (zero ? 0 : 1) || value > MAX) throw new Error('請輸入有效整數點數')
  return value
}
export function taipei(value: string): string {
  return new Intl.DateTimeFormat('zh-TW', { timeZone: 'Asia/Taipei', dateStyle: 'short', timeStyle: 'medium', hour12: false }).format(new Date(value))
}

export function signedPoints(value: number): number {
  if (!Number.isSafeInteger(value) || Math.abs(value) > MAX) throw new Error('請輸入安全範圍內的整數點數')
  return value
}
export function roleLabel(value: string): string { return ({ Admin: '管理員', Staff: '員工' } as Record<string, string>)[value] || value }
export function transactionLabel(value: string): string { return ({ GRANT: '發點', REDEEM: '扣點', ADJUST: '餘額調整' } as Record<string, string>)[value] || value }
