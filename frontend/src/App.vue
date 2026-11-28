<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { parseToken, points, signedPoints, taipei, requestId, roleLabel, transactionLabel } from './logic'
import CameraScanner from './CameraScanner.vue'
import MemberPortal from './MemberPortal.vue'
import { requestJson } from './request'
import { templateRedemption, type RedeemTemplate } from './redeemTemplates'
type User = { id: string; member_code: string; display_name: string; balance: number; status: string }
type Operator = { id: string; username: string; role: string; csrf: string }
type Tx = { member_name: string; member_code: string; operator_name: string; id: string; user_id: string; operator_id: string; type: string; delta: number; balance_before: number; balance_after: number; reason: string; station_id: string; created_at: string; occurred_at: string }
const editing = ref<User | null>(null), editCode = ref(''), editName = ref(''), occurredAt = ref('')
const importFile = ref<File | null>(null)
const healthError = ref('')
const redeemTemplates = ref<RedeemTemplate[]>([]), templateDrafts = ref<RedeemTemplate[]>([]), selectedTemplateId = ref('')
const portal = ref(false), oldPassword = ref(''), changedPassword = ref(''), confirmPassword = ref(''), resetTarget = ref(''), resetPassword = ref('')
const me = ref<Operator | null>(null), online = ref(false), busy = ref(false), message = ref(''), error = ref(false)
const tab = ref('掃碼核銷'), username = ref(''), password = ref(''), users = ref<User[]>([]), query = ref('')
const memberCode = ref(''), displayName = ref(''), selected = ref<User | null>(null), token = ref(''), scanInput = ref<HTMLInputElement | null>(null)
const amount = ref(100), reason = ref('現場核銷'), mode = ref('redeem'), transactions = ref<Tx[]>([])
const station = ref(localStorage.getItem('station') || 'PC-' + requestId().slice(0, 8))
const config = ref({ grant_presets: [50, 100, 200], staff_limit: 200, backup_hour: 2, backup_keep: 14 })
const presetsText = ref('50,100,200'), operators = ref<Array<{ id: string; username: string; role: string; status: string }>>([])
const newName = ref(''), newPassword = ref(''), newRole = ref('Staff'), backupNames = ref<string[]>([])
const qrUser = ref<User | null>(null), filterUser = ref(''), filterKind = ref(''), filterOperator = ref(''), filterStart = ref(''), filterEnd = ref(''), txPage = ref(0)
const pending = ref<{ key: string; path: string; body: Record<string, unknown> } | null>(null)
const isAdmin = computed(() => me.value?.role === 'Admin')
const tabs = computed(() => ['掃碼核銷', '會員管理', '點數發放', '交易紀錄', '修改密碼', ...(isAdmin.value ? ['扣點模板', '操作員管理', '系統設定', '備份還原'] : [])])
const preview = computed(() => selected.value ? mode.value === 'adjust' ? amount.value : selected.value.balance + (mode.value === 'redeem' ? -amount.value : amount.value) : 0)
let timer: ReturnType<typeof setInterval>
async function cameraDecoded(value: string) { token.value = value; await lookup() }
const secureTransport = window.location.protocol === 'https:'
async function changePassword() { await run(async () => { if (changedPassword.value !== confirmPassword.value) throw new Error('兩次新密碼不一致'); await api('/auth/password', 'POST', { current_password: oldPassword.value, new_password: changedPassword.value }); oldPassword.value = ''; changedPassword.value = ''; confirmPassword.value = ''; me.value = null; selected.value = null; token.value = ''; notify('密碼已修改，請使用新密碼登入') }) }
async function resetStaffPassword() { await run(async () => { await api('/operators/' + resetTarget.value + '/password', 'POST', { new_password: resetPassword.value }); resetPassword.value = ''; resetTarget.value = ''; notify('員工密碼已重設，原登入已失效') }) }
function printQr() { window.print() }
class ApiError extends Error { constructor(public status: number, message: string) { super(message) } }
function notify(text: string, failed = false) { message.value = text; error.value = failed }
async function api(path: string, method = 'GET', body?: unknown) {
  const { response, data } = await requestJson('/api' + path, { method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(me.value ? { 'X-CSRF-Token': me.value.csrf } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) })
  if (!response.ok) {
    const result = data
    if (response.status === 401 && path !== '/auth/login') me.value = null
    throw new ApiError(response.status, typeof result.detail === 'string' ? result.detail : '輸入資料不符合規則')
  }
  return data
}
async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  try { await action() } catch (e) { notify(e instanceof Error ? e.message : '操作失敗', true) } finally { busy.value = false }
}
async function loadConfig() { config.value = { ...config.value, ...await api('/settings') }; presetsText.value = config.value.grant_presets.join(','); await loadRedeemTemplates() }
async function loadRedeemTemplates() { redeemTemplates.value = await api('/redeem-templates') }
function applyRedeemTemplate(template: RedeemTemplate) {
  if (busy.value || pending.value) return
  const choice = templateRedemption(template)
  selectedTemplateId.value = choice.redeem_template_id; amount.value = choice.amount; reason.value = choice.reason
}
function manualRedeem() { selectedTemplateId.value = ''; amount.value = 100; reason.value = '現場核銷' }
function addRedeemTemplate() { if (templateDrafts.value.length < 50) templateDrafts.value.push({ id: requestId(), name: '', points: 100 }) }
async function saveRedeemTemplates() { await run(async () => {
  const templates = templateDrafts.value.map(t => ({ ...t, name: t.name.trim(), points: points(t.points) }))
  if (templates.some(t => !t.name)) throw new Error('請填寫每個商品名稱')
  if (new Set(templates.map(t => t.name.toLowerCase())).size !== templates.length) throw new Error('商品名稱不可重複')
  redeemTemplates.value = await api('/redeem-templates', 'PUT', { templates })
  templateDrafts.value = redeemTemplates.value.map(t => ({ ...t })); notify('扣點模板已儲存，所有設備可共用')
}) }
async function login() { await run(async () => { me.value = await api('/auth/login', 'POST', { username: username.value, password: password.value }); password.value = ''; await loadConfig(); loadPending(); notify('登入成功'); await nextTick(); scanInput.value?.focus() }) }
async function logout() {
  await run(async () => { await api('/auth/logout', 'POST'); oldPassword.value = ''; changedPassword.value = ''; confirmPassword.value = ''; resetPassword.value = ''; resetTarget.value = ''; me.value = null; selected.value = null; qrUser.value = null; users.value = []; transactions.value = []; token.value = ''; pending.value = null; notify('已登出') })
}
function pendingStorage() { return 'pending-' + me.value?.id + '-' + station.value }
function loadPending() {
  try { pending.value = JSON.parse(localStorage.getItem(pendingStorage()) || 'null') } catch { pending.value = null }
}
function savePending() {
  // QR credentials stay in memory; persistent recovery only needs the idempotency key.
  if (pending.value) localStorage.setItem(pendingStorage(), JSON.stringify({ ...pending.value, body: {} }))
  else localStorage.removeItem(pendingStorage())
}
async function search() { users.value = await api('/users?q=' + encodeURIComponent(query.value)) }
async function createMember() { await run(async () => { await api('/users', 'POST', { member_code: memberCode.value, display_name: displayName.value }); memberCode.value = ''; displayName.value = ''; await search(); notify('會員已建立，可顯示 QR') }) }
function editMember(user: User) { editing.value = user; editCode.value = user.member_code; editName.value = user.display_name }
async function saveMember() { await run(async () => { if (!editing.value) return; await api('/users/' + editing.value.id, 'PUT', { member_code: editCode.value, display_name: editName.value }); editing.value = null; await search(); notify('會員資料已更新，原 QR 與交易紀錄繼續有效') }) }
function selectImport(event: Event) { importFile.value = (event.target as HTMLInputElement).files?.[0] || null }
async function importMembers() { await run(async () => {
  if (!importFile.value) throw new Error('請先選擇 Excel 檔案')
  if (importFile.value.size > 5 * 1024 * 1024) throw new Error('檔案不得超過 5 MB')
  const { response, data: result } = await requestJson('/api/users/import', { method: 'POST', headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'X-CSRF-Token': me.value!.csrf }, body: importFile.value }, 60000)
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '匯入失敗')
  importFile.value = null; await search(); notify(`已匯入 ${result.imported} 位會員`)
}) }
async function lookup() { await run(async () => { if (pending.value) throw new Error('請先查證待確認的交易'); await loadRedeemTemplates(); selectedTemplateId.value = ''; const scanned = parseToken(token.value); selected.value = await api('/scan/lookup', 'POST', { token: scanned }); token.value = scanned; occurredAt.value = ''; amount.value = 100; reason.value = '現場核銷'; mode.value = 'redeem'; notify('請核對會員並確認扣點') }) }
async function submit() {
  await run(async () => {
    if (!selected.value || pending.value) throw new Error('請先選擇會員並查證未完成交易')
    if (mode.value === 'adjust') signedPoints(amount.value)
    else points(amount.value)
    if (!reason.value.trim()) throw new Error('請填寫原因')
    if (isAdmin.value && occurredAt.value) {
      const date = new Date(occurredAt.value + '+08:00')
      if (!Number.isFinite(date.getTime()) || date.getTime() > Date.now()) throw new Error('請指定有效的過去交易日期')
    }
    const body = { user_id: selected.value.id, amount: amount.value, reason: reason.value, station_id: station.value, idempotency_key: requestId(), ...(isAdmin.value && occurredAt.value ? { occurred_at: new Date(occurredAt.value + '+08:00').toISOString() } : {}), ...(mode.value === 'redeem' ? { token: parseToken(token.value), ...(selectedTemplateId.value ? { redeem_template_id: selectedTemplateId.value } : {}) } : {}) }
    pending.value = { key: body.idempotency_key, path: '/transactions/' + mode.value, body }; savePending()
    try {
      const result: Tx = await api(pending.value.path, 'POST', body)
      pending.value = null; savePending(); selected.value = null; token.value = ''
      notify(`交易成功｜${result.id}｜${result.balance_before} → ${result.balance_after} 點｜${taipei(result.created_at)}`)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && ['商品模板已刪除，請重新選擇商品', '商品點數已變更，請重新載入並選擇商品'].includes(e.message)) {
        pending.value = null; savePending(); manualRedeem();
        try { await loadRedeemTemplates() } catch { /* retry loading on the next scan */ }
        notify(e.message + '，此筆未扣點', true); return
      }
      notify('結果待確認，請按「查證交易」；勿另建相同操作。' + (e instanceof Error ? e.message : ''), true) }
  })
}
async function verifyPending() { await run(async () => {
  if (!pending.value) return
  const result: Tx = await api('/transactions/by-key/' + pending.value.key)
  pending.value = null; savePending(); selected.value = null; token.value = ''
  notify(`已查證交易成功｜${result.id}｜餘額 ${result.balance_after} 點`)
}) }
async function retryPending() { await run(async () => {
  if (!pending.value || !pending.value.body.idempotency_key) throw new Error('重新載入後僅保留查證鍵。請管理員查核伺服器交易紀錄，再解除待確認狀態')
  const result = await api(pending.value.path, 'POST', pending.value.body)
  pending.value = null; savePending(); selected.value = null; token.value = ''; notify(`交易已確認｜${result.id}｜餘額 ${result.balance_after}`)
}) }
function clearPending() { if (window.confirm('請先由管理員確認伺服器已完成處理並核對流水帳。確定解除待確認狀態？此動作不會取消伺服器交易。')) { pending.value = null; savePending() } }
function choose(user: User) { selectedTemplateId.value = ''; selected.value = user; occurredAt.value = ''; mode.value = 'grant'; amount.value = config.value.grant_presets[0]; reason.value = '現場發點'; tab.value = '點數發放' }
async function reissue(user: User) { if (window.confirm('重發後舊 QR 立即失效，確定重發？')) await run(async () => { await api('/users/' + user.id + '/qr/reissue', 'POST'); qrUser.value = user; notify('已重發，舊憑證失效') }) }
async function statusUser(user: User) { await run(async () => { await api('/users/' + user.id, 'PATCH', { status: user.status === 'active' ? 'disabled' : 'active' }); await search(); notify('狀態已更新') }) }
function filters() { return new URLSearchParams({ member_code: filterUser.value, kind: filterKind.value, operator_id: filterOperator.value, start: filterStart.value ? new Date(filterStart.value + '+08:00').toISOString() : '', end: filterEnd.value ? new Date(filterEnd.value + '+08:00').toISOString() : '' }).toString() }
async function loadTransactions() { transactions.value = await api('/transactions?' + filters() + '&offset=' + txPage.value * 100) }
async function createOperator() { await run(async () => { await api('/operators', 'POST', { username: newName.value, password: newPassword.value, role: newRole.value }); newPassword.value = ''; newName.value = ''; operators.value = await api('/operators'); notify('已新增操作員') }) }
async function statusOperator(id: string, status: string) { await run(async () => { await api('/operators/' + id, 'PATCH', { status: status === 'active' ? 'disabled' : 'active' }); operators.value = await api('/operators') }) }
async function saveConfig() { await run(async () => { config.value.grant_presets = presetsText.value.split(',').map(Number); await api('/settings', 'PUT', config.value); notify('設定已儲存') }) }
async function backup() { await run(async () => { const result = await api('/backup', 'POST'); backupNames.value = await api('/backups'); notify('一致性備份完成：' + result.filename) }) }
watch(tab, async () => {
  if (tab.value !== '修改密碼') { oldPassword.value = ''; changedPassword.value = ''; confirmPassword.value = '' }
  if (tab.value !== '操作員管理') { resetPassword.value = ''; resetTarget.value = '' }
  qrUser.value = null
  await run(async () => {
    if (tab.value === '會員管理' || tab.value === '點數發放') await search()
    if (tab.value === '扣點模板') { await loadRedeemTemplates(); templateDrafts.value = redeemTemplates.value.map(t => ({ ...t })) }
    if (tab.value === '交易紀錄') { txPage.value = 0; await loadTransactions() }
    if (tab.value === '操作員管理') operators.value = await api('/operators')
    if (tab.value === '備份還原') backupNames.value = await api('/backups')
    if (tab.value === '掃碼核銷') { selectedTemplateId.value = ''; mode.value = 'redeem'; selected.value = null; await nextTick(); scanInput.value?.focus() }
  })
})
watch(station, () => { localStorage.setItem('station', station.value); loadPending() })
async function health() {
  try {
    const result = await api('/health')
    if (result?.status !== 'ok') throw new Error('健康檢查回應不正確，請確認 API 網址')
    online.value = true; healthError.value = ''
  } catch (error) { online.value = false; healthError.value = error instanceof Error ? error.message : '連線檢查失敗' }
}
onMounted(async () => { await health(); try { me.value = await api('/auth/me'); await loadConfig(); loadPending() } catch { /* login required */ } timer = setInterval(health, 10000) })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <header><div><span class="logo">QR</span><strong>點數管理系統</strong><small>私人區域網路</small></div><div><span :class="['status', online ? 'up' : 'down']">{{ online ? '● 伺服器已連線' : '● 無法連線' }}</span><span v-if="me">{{ me.username }} · {{ roleLabel(me.role) }} <button @click="logout" :disabled="busy">登出</button></span></div></header>
  <div class="notice">{{ secureTransport ? '目前使用 HTTPS 加密連線。' : 'HTTP 傳輸未加密，僅適用隔離且可信任的區域網路；其他裝置即時相機需改用 HTTPS。' }}靜態會員圖碼可被複製，核銷前請核對會員身分。</div>
  <MemberPortal v-if="portal && !me" @close="portal = false" />
  <main v-else-if="!me" class="login"><h1>操作員登入</h1><button @click="portal = true">一般使用者查詢</button><p>請使用管理員建立的本機帳號</p><form @submit.prevent="login"><label>帳號<input v-model="username" autocomplete="username" required></label><label>密碼<input v-model="password" type="password" autocomplete="current-password" required></label><button class="primary" :disabled="busy || !online">登入</button></form><p v-if="!online && healthError" role="alert">{{ healthError }}。可在同一台設備開啟 <a href="/api/health" target="_blank" rel="noopener">API 連線檢查</a> 協助排錯。</p><p>首次使用請於 PC-01 執行 QRPointServer.exe init。</p></main>
  <div v-else class="layout"><aside><nav><button v-for="item in tabs" :key="item" :class="{ active: tab === item }" @click="tab = item">{{ item }}</button></nav><label class="station">工作站識別<input v-model="station" maxlength="80" :disabled="!!pending || busy"></label><small>工作站識別為操作紀錄標記</small></aside>
    <main><div class="title"><h1>{{ tab }}</h1><span>點數作業 · 台北時間</span></div>
      <section v-if="pending" class="pending"><h2>交易結果待確認</h2><p>冪等鍵：{{ pending.key }}</p><button @click="verifyPending" :disabled="busy || !online">查證交易</button><button @click="retryPending" :disabled="busy || !online">以原鍵重試</button><button v-if="isAdmin" @click="clearPending">已人工核對，解除狀態</button></section>
      <template v-if="tab === '掃碼核銷'">
        <section><h2>01 掃描會員 QR</h2><p>USB 掃描器以 Enter 結尾，或貼上會員憑證後查詢。</p><form @submit.prevent="lookup" class="inline"><input ref="scanInput" v-model="token" placeholder="請掃描或輸入會員憑證" aria-label="QR Token" :disabled="busy || !!pending || !!selected" ><button class="primary" :disabled="busy || !online || !!pending || !!selected">查詢會員</button></form><CameraScanner v-if="!pending && !selected" @decoded="cameraDecoded" /></section>
      </template>
      <template v-if="tab === '會員管理' || (tab === '點數發放' && !selected)">
        <section v-if="tab === '會員管理'"><h2>新增會員</h2><form @submit.prevent="createMember" class="inline"><input v-model="memberCode" placeholder="會員編號" aria-label="會員編號" required maxlength="80"><input v-model="displayName" placeholder="顯示名稱" aria-label="顯示名稱" required maxlength="100"><button class="primary" :disabled="busy || !online">建立會員</button></form></section>
        <section v-if="tab === '會員管理' && isAdmin"><h2>Excel 批次匯入會員</h2><p>使用 .xlsx，第一列前兩欄為「會員編號」「會員名稱」。編號建議設為文字以保留前導零；每次最多 2000 列、5 MB。重複編號或錯誤會取消整批匯入。</p><form @submit.prevent="importMembers"><input type="file" accept=".xlsx" aria-label="匯入會員 Excel" @change="selectImport"><button :disabled="busy || !online || !importFile">匯入會員</button></form></section>
        <section><form @submit.prevent="run(search)" class="inline"><input v-model="query" placeholder="搜尋編號或名稱" aria-label="搜尋會員"><button :disabled="busy">搜尋</button></form><p>最多顯示 100 筆，請用搜尋縮小範圍。</p><div class="table"><table><thead><tr><th>編號 / 名稱</th><th>點數</th><th>狀態</th><th>操作</th></tr></thead><tbody><tr v-for="user in users" :key="user.id"><td>{{ user.member_code }}<br><strong>{{ user.display_name }}</strong></td><td class="balance">{{ user.balance }}</td><td>{{ user.status === 'active' ? '啟用' : '停用' }}</td><td><button @click="choose(user)" :disabled="user.status !== 'active' || !!pending">發點 / 調整</button><button v-if="isAdmin" @click="editMember(user)" :disabled="busy">編輯編號 / 名稱</button><button @click="qrUser = user">QR</button><button @click="reissue(user)" :disabled="busy">重發</button><button v-if="isAdmin" @click="statusUser(user)" :disabled="busy">{{ user.status === 'active' ? '停用' : '啟用' }}</button></td></tr></tbody></table></div></section>
      </template>
      <section v-if="selected && (tab === '掃碼核銷' || tab === '點數發放')"><h2>{{ selected.display_name }} <small>{{ selected.member_code }}</small></h2><p class="balance">{{ selected.balance }} <small>目前點數</small></p>
        <form @submit.prevent="submit"><label v-if="tab === '點數發放' && isAdmin">操作類型<select v-model="mode"><option value="grant">發放點數</option><option value="redeem">扣減點數（需掃描 QR）</option><option value="adjust">設定目標餘額</option></select></label>
          <label v-if="mode === 'redeem' && tab === '點數發放'">會員憑證<input v-model="token" required></label>
          <div v-if="mode === 'grant'" class="presets"><button v-for="n in config.grant_presets.filter(n => isAdmin || n <= config.staff_limit)" type="button" @click="amount = n">+{{ n }}</button></div>
          <div v-if="mode === 'redeem'" class="redeem-products"><h3>快速扣點商品</h3><div class="presets"><button v-for="product in redeemTemplates" :key="product.id" type="button" :class="{ primary: selectedTemplateId === product.id }" @click="applyRedeemTemplate(product)" :disabled="busy || !!pending">{{ product.name }} · {{ product.points }} 點</button><button type="button" @click="manualRedeem" :disabled="busy || !!pending">自訂扣點</button></div><p v-if="!redeemTemplates.length">尚無商品模板，管理員可在「扣點模板」新增。</p><small v-if="selectedTemplateId">已選擇商品；請核對點數與預估餘額，再按確認扣點。</small></div>
          <label>{{ mode === 'adjust' ? '目標餘額' : mode === 'grant' ? '發放點數' : '扣除點數' }}<input v-if="isAdmin || mode !== 'grant'" v-model.number="amount" :disabled="mode === 'redeem' && !!selectedTemplateId" type="number" :min="mode === 'adjust' ? -4503599627370495 : 0.5" :max="4503599627370495" step="0.5" required><select v-else v-model.number="amount"><option v-for="n in config.grant_presets.filter(n => n <= config.staff_limit)" :value="n">{{ n }}</option></select></label>
          <label v-if="isAdmin">交易日期（台北時間，留空為現在）<input v-model="occurredAt" type="datetime-local"></label><p v-if="isAdmin && occurredAt">補登會更新目前餘額；歷史交易的前後餘額仍依實際登錄順序保留。</p><label>操作原因<input v-model="reason" required :maxlength="selectedTemplateId ? 350 : 500"></label><div class="estimate">預估：{{ selected.balance }} → <strong>{{ preview }}</strong> 點 <small>以伺服器交易結果為準</small></div><button class="primary" :disabled="busy || !online || !!pending">{{ mode === 'redeem' ? '確認扣點' : mode === 'adjust' ? '確認修正餘額' : '確認發點' }}</button><button type="button" @click="selected = null; token = ''; nextTick(() => scanInput?.focus())" :disabled="busy || !!pending">{{ tab === '掃碼核銷' ? '掃描下一位' : '選擇其他會員' }}</button></form>
      </section>
      <section v-if="tab === '交易紀錄'"><form @submit.prevent="run(async () => { txPage = 0; await loadTransactions() })" class="filters"><label>會員編號<input v-model="filterUser" placeholder="例如 049（完整編號）"></label><label>交易類型<select v-model="filterKind"><option value="">全部</option><option value="GRANT">發點</option><option value="REDEEM">扣點</option><option value="ADJUST">餘額調整</option></select></label><label v-if="isAdmin">操作員識別碼<input v-model="filterOperator"></label><label>開始<input v-model="filterStart" type="datetime-local"></label><label>結束<input v-model="filterEnd" type="datetime-local"></label><button :disabled="busy">查詢</button><a :href="'/api/transactions/export?' + filters()" class="button">匯出 CSV</a></form><div class="table"><table><thead><tr><th>時間 / 交易編號</th><th>會員 / 操作員</th><th>種類</th><th>增減</th><th>前 → 後</th><th>原因 / 工作站</th></tr></thead><tbody><tr v-for="tx in transactions" :key="tx.id"><td>{{ taipei(tx.occurred_at || tx.created_at) }}<small>登錄：{{ taipei(tx.created_at) }}</small><small class="id">{{ tx.id }}</small></td><td><small class="id">{{ tx.member_name }}（{{ tx.member_code }}）<br>{{ tx.operator_name }}</small></td><td>{{ transactionLabel(tx.type) }}</td><td>{{ tx.delta }}</td><td>{{ tx.balance_before }} → {{ tx.balance_after }}</td><td>{{ tx.reason }}<br><small>{{ tx.station_id }}</small></td></tr></tbody></table></div><button :disabled="txPage === 0 || busy" @click="run(async () => { txPage--; await loadTransactions() })">上一頁</button><span>第 {{ txPage + 1 }} 頁</span><button :disabled="transactions.length < 100 || busy" @click="run(async () => { txPage++; await loadTransactions() })">下一頁</button></section>
      <section v-if="tab === '操作員管理'"><h2>新增操作員</h2><form @submit.prevent="createOperator" class="inline"><input v-model="newName" placeholder="帳號" aria-label="新操作員帳號" required><input v-model="newPassword" type="password" placeholder="密碼至少 12 碼，含字母數字" aria-label="新操作員密碼" minlength="12" autocomplete="new-password" required><select v-model="newRole"><option value="Staff">員工</option><option value="Admin">管理員</option></select><button :disabled="busy">新增</button></form><ul><li v-for="op in operators" :key="op.id">{{ op.username }} · {{ roleLabel(op.role) }} · {{ op.status === 'active' ? '啟用' : '停用' }} <small>{{ op.id }}</small><button :disabled="op.id === me?.id || busy" @click="statusOperator(op.id, op.status)">{{ op.status === 'active' ? '停用' : '啟用' }}</button><button v-if="op.role === 'Staff'" @click="resetTarget = op.id; resetPassword = ''" :disabled="busy">重設密碼</button></li></ul><form v-if="resetTarget" @submit.prevent="resetStaffPassword"><h2>重設員工密碼</h2><label>新密碼<input v-model="resetPassword" type="password" minlength="12" maxlength="128" autocomplete="new-password" required></label><button :disabled="busy">確認重設</button><button type="button" @click="resetTarget = ''; resetPassword = ''">取消</button></form></section>
      <section v-if="tab === '修改密碼'"><h2>修改自己的登入密碼</h2><p>修改後，本帳號所有裝置的登入都會失效，請重新登入。</p><form @submit.prevent="changePassword"><label>目前密碼<input v-model="oldPassword" type="password" autocomplete="current-password" required maxlength="128"></label><label>新密碼<input v-model="changedPassword" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></label><label>確認新密碼<input v-model="confirmPassword" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></label><button class="primary" :disabled="busy">儲存新密碼</button></form></section>
      <section v-if="tab === '扣點模板' && isAdmin"><h2>自訂商品與消耗點數</h2><p>新增、修改或移除後按「儲存模板」。每次扣點只選一項商品，支援 0.5 點；操作員掃描會員後可快速套用，仍需確認扣點。最多 50 項。</p><form @submit.prevent="saveRedeemTemplates"><div class="table"><table><thead><tr><th>商品名稱</th><th>消耗點數</th><th>操作</th></tr></thead><tbody><tr v-for="(product, index) in templateDrafts" :key="product.id"><td><input v-model="product.name" required maxlength="100" aria-label="商品名稱" :disabled="busy"></td><td><input v-model.number="product.points" type="number" min="0.5" :max="4503599627370495" step="0.5" required aria-label="消耗點數" :disabled="busy"></td><td><button type="button" @click="templateDrafts.splice(index, 1)" :disabled="busy">移除</button></td></tr></tbody></table></div><p v-if="!templateDrafts.length">尚無商品，請按「新增商品」。</p><button type="button" @click="addRedeemTemplate" :disabled="busy || templateDrafts.length >= 50">新增商品</button><button class="primary" :disabled="busy || !online">儲存模板</button></form></section>
      <section v-if="tab === '系統設定'"><form @submit.prevent="saveConfig"><label>固定發點額度（逗號分隔）<input v-model="presetsText" required></label><label>員工單筆發點上限<input v-model.number="config.staff_limit" type="number" min="0.5" step="0.5" required></label><label>每日備份時間（台北時間 0–23 時）<input v-model.number="config.backup_hour" type="number" min="0" max="23" required></label><label>每日備份保留份數<input v-model.number="config.backup_keep" type="number" min="1" max="365" required></label><button class="primary" :disabled="busy">儲存設定</button></form></section>
      <section v-if="tab === '備份還原'"><h2>資料備份</h2><p>使用資料庫備份機制產生一致的備份檔。請一併安全保存 secret.key 與設定，並定期複製至外接儲存或異機。</p><button class="primary" @click="backup" :disabled="busy || !online">立即備份</button><ul><li v-for="name in backupNames" :key="name">{{ name }}</li></ul><h2>管理員還原</h2><p>在 PC-01 先執行 stop_server.bat，等待伺服器停止，再執行下列命令並輸入管理員帳密。還原前會自動備份目前資料，驗證完整性、外鍵、資料庫結構版本與憑證金鑰；完成後重新啟動。</p><code>QRPointServer.exe restore --file "完整備份路徑.db"</code><p>還原會清除登入狀態；如服務仍運作，獨占鎖會拒絕還原。</p></section>
    </main>
  </div>
  <dialog :open="!!editing" v-if="editing"><h2>編輯會員</h2><form @submit.prevent="saveMember"><label>會員編號<input v-model="editCode" maxlength="80" required></label><label>會員名稱<input v-model="editName" maxlength="100" required></label><button :disabled="busy">儲存</button><button type="button" @click="editing = null" :disabled="busy">取消</button></form></dialog>
  <dialog :open="!!qrUser" v-if="qrUser" class="qr"><div class="print-area"><h2>{{ qrUser.display_name }}</h2><p>{{ qrUser.member_code }} · 顯示時餘額 {{ qrUser.balance }} 點</p><img :src="'/api/users/' + qrUser.id + '/qr'" alt="會員 QR 憑證" width="280" height="280"><p>靜態憑證，請妥善保管</p></div><a :href="'/api/users/' + qrUser.id + '/qr'" download="member-qr.png" class="button">下載 PNG</a><button @click="printQr">列印</button><button @click="qrUser = null">關閉</button></dialog>
  <div v-if="message" role="status" :class="['message', { error }]">{{ message }}<button @click="message = ''" aria-label="關閉提示">×</button></div>
</template>
