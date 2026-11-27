// Do not depend on AbortSignal.timeout(): older mobile browsers lack it.
// Keep the deadline active until the response body has also been read.
export async function requestJson(url: string, init: RequestInit = {}, timeoutMs = 15000) {
  if (typeof AbortController === 'undefined') throw new Error('瀏覽器版本過舊，請更新 Safari 或 Chrome')
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, { ...init, signal: controller.signal })
    let data
    try { data = await response.json() }
    catch (error) {
      if (controller.signal.aborted) throw error
      if (response.ok) throw new Error('伺服器回傳非預期資料，請確認目前網址與 API 設定')
      data = { detail: `伺服器錯誤（HTTP ${response.status}）` }
    }
    return { response, data }
  } catch (error) {
    if (controller.signal.aborted) throw new Error('連線逾時，請檢查 Wi-Fi 與伺服器；已送出的交易請先查證')
    if (error instanceof TypeError) throw new Error('無法連線至 API，請檢查 Wi-Fi、HTTPS 憑證信任與伺服器網址')
    throw error
  } finally { clearTimeout(timer) }
}
