import { afterEach, describe, expect, it, vi } from 'vitest'
import { requestJson } from './request'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('手機 API 連線', () => {
  it('沒有 AbortSignal.timeout 仍可完成健康檢查', async () => {
    vi.stubGlobal('AbortSignal', {})
    const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: 'ok' }) })
    vi.stubGlobal('fetch', fetch)
    const result = await requestJson('/api/health')
    expect(result.data).toEqual({ status: 'ok' })
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('回傳 HTTP 錯誤供呼叫端處理，不重試交易', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: '限管理員' }) })
    vi.stubGlobal('fetch', fetch)
    const result = await requestJson('/api/transactions/grant', { method: 'POST', body: '{}' })
    expect(result.response.status).toBe(403)
    expect(result.data.detail).toBe('限管理員')
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('逾時會取消請求，顯示查證提示並清除計時器', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn((_url, options) => new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new Error('aborted')))
    })))
    const outcome = expect(requestJson('/api/health', {}, 50)).rejects.toThrow('連線逾時')
    await vi.advanceTimersByTimeAsync(50)
    await outcome
    expect(vi.getTimerCount()).toBe(0)
  })

  it('伺服器送出標頭後，讀取本文仍受逾時限制', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn(async (_url, options) => ({
      ok: true, status: 200,
      json: () => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('aborted body')))),
    })))
    const outcome = expect(requestJson('/api/health', {}, 50)).rejects.toThrow('連線逾時')
    await vi.advanceTimersByTimeAsync(50)
    await outcome
    expect(vi.getTimerCount()).toBe(0)
  })

  it('HTML 回應不會誤認為健康的 API', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => { throw new SyntaxError('HTML') } }))
    await expect(requestJson('/api/health')).rejects.toThrow('非預期資料')
  })
})
