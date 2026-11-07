<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import CameraScanner from './CameraScanner.vue'
import { parseToken, taipei, transactionLabel } from './logic'
const emit = defineEmits<{ close: [] }>()
type Member = { member_code: string; display_name: string; balance: number }
type Tx = { id: string; type: string; delta: number; balance_before: number; balance_after: number; reason: string; created_at: string; member_name: string; operator_name: string }
const token = ref(''), me = ref<Member | null>(null), rows = ref<Tx[]>([]), busy = ref(false), message = ref(''), page = ref(0)
async function request(path: string, method = 'GET', body?: unknown) {
  const response = await fetch('/api/portal' + path, { method, headers: { 'Content-Type': 'application/json', 'X-Portal-Action': 'logout' }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(15000) })
  if (!response.ok) { if (response.status === 401) { me.value = null; rows.value = [] }; const error = await response.json(); throw new Error(typeof error.detail === 'string' ? error.detail : '查詢失敗，請稍後再試') }
  return response.json()
}
async function refresh() { me.value = await request('/me'); rows.value = await request('/transactions?offset=' + page.value * 50) }
async function run(action: () => Promise<void>) { if (busy.value) return; busy.value = true; message.value = ''; try { await action() } catch (e) { message.value = e instanceof Error ? e.message : '無法連線，請稍後再試' } finally { busy.value = false } }
async function lookup() { await run(async () => { await request('/login', 'POST', { token: parseToken(token.value) }); token.value = ''; page.value = 0; await refresh() }) }
async function decoded(value: string) { token.value = value; await lookup() }
async function leave(close = false) { await run(async () => { await request('/logout', 'POST'); me.value = null; rows.value = []; token.value = ''; if (close) emit('close') }) }
let expiryCheck: ReturnType<typeof setInterval>
onMounted(async () => { try { await refresh() } catch { /* scan required */ }; expiryCheck = setInterval(async () => { if (me.value && !busy.value) { try { await refresh() } catch { me.value = null; rows.value = []; message.value = '查詢已逾時或無法連線，請重新掃描會員憑證' } } }, 30000) })
onUnmounted(() => clearInterval(expiryCheck))
</script>
<template><main class="member-portal"><div class="title"><h1>一般使用者查詢</h1><button @click="leave(true)" :disabled="busy">返回操作員登入</button></div><section v-if="!me"><h2>掃描自己的會員憑證</h2><p>僅能查詢憑證所屬會員的點數與交易紀錄，不提供點數異動。請妥善保管圖碼，避免他人取得後查看資料。</p><form @submit.prevent="lookup" class="inline"><input v-model="token" placeholder="掃描或輸入會員憑證" aria-label="會員查詢憑證" required><button class="primary" :disabled="busy">查詢我的點數</button></form><CameraScanner @decoded="decoded" /></section><template v-else><section><h2>{{ me.display_name }} <small>{{ me.member_code }}</small></h2><p class="balance" :class="{ negative: me.balance < 0 }">{{ me.balance }} 點</p><p>查詢登入有效時間為十分鐘。共用設備使用完畢後請登出。</p><button @click="run(refresh)" :disabled="busy">重新整理</button><button @click="leave()" :disabled="busy">結束查詢並登出</button></section><section><h2>我的交易紀錄</h2><div class="table"><table><thead><tr><th>時間</th><th>種類</th><th>增減</th><th>前 → 後</th><th>操作人員</th><th>原因</th></tr></thead><tbody><tr v-for="tx in rows" :key="tx.id"><td>{{ taipei(tx.created_at) }}</td><td>{{ transactionLabel(tx.type) }}</td><td>{{ tx.delta }}</td><td>{{ tx.balance_before }} → {{ tx.balance_after }}</td><td>{{ tx.operator_name }}</td><td>{{ tx.reason }}</td></tr></tbody></table><p v-if="!rows.length">尚無交易紀錄</p></div><button :disabled="page === 0 || busy" @click="run(async () => { page--; await refresh() })">上一頁</button><span>第 {{ page + 1 }} 頁</span><button :disabled="rows.length < 50 || busy" @click="run(async () => { page++; await refresh() })">下一頁</button></section></template><p v-if="message" role="status">{{ message }}</p></main></template>
