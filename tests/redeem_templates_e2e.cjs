const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const baseURL = process.env.TEST_URL || 'http://localhost:18089';
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const context = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/');
    await page.getByLabel('帳號', { exact: true }).fill('test-admin');
    await page.getByLabel('密碼', { exact: true }).fill('Only-For-Tests-9284');
    await page.getByRole('button', { name: '登入', exact: true }).click();
    await page.getByRole('button', { name: '扣點模板', exact: true }).click();
    await page.getByRole('button', { name: '新增商品', exact: true }).click();
    await page.getByLabel('商品名稱', { exact: true }).fill('咖啡');
    await page.getByLabel('消耗點數', { exact: true }).fill('50.5');
    await page.getByRole('button', { name: '儲存模板', exact: true }).click();
    await page.getByRole('status').filter({ hasText: '扣點模板已儲存' }).waitFor();
    const identity = await (await context.request.get('/api/auth/me')).json();
    const headers = { 'X-CSRF-Token': identity.csrf };
    const memberResponse = await context.request.post('/api/users', { headers, data: { member_code: 'E2E-TEMPLATE', display_name: '商品測試會員' } });
    assert.equal(memberResponse.status(), 200);
    const member = await memberResponse.json();
    const templates = await (await context.request.get('/api/redeem-templates')).json();
    await page.getByRole('button', { name: '掃碼核銷', exact: true }).click();
    async function scan() {
      await page.getByLabel('QR Token', { exact: true }).fill(member.token);
      await page.getByRole('button', { name: '查詢會員', exact: true }).click();
      await page.getByRole('button', { name: '咖啡 · 50.5 點', exact: true }).click();
    }
    await scan();
    assert.equal(await page.getByLabel('扣除點數', { exact: true }).inputValue(), '50.5');
    assert.equal(await page.getByLabel('扣除點數', { exact: true }).isDisabled(), true);
    assert.deepEqual(await (await context.request.get('/api/transactions')).json(), []);
    await page.screenshot({ path: process.env.TEST_SCREENSHOT || 'work/redeem-template-mobile.png', fullPage: true });
    await page.getByRole('button', { name: '確認扣點', exact: true }).click();
    await page.getByRole('status').filter({ hasText: '交易成功' }).waitFor();
    const first = await (await context.request.get('/api/transactions')).json();
    assert.equal(first.length, 1);
    assert.equal(first[0].delta, -50.5);
    assert.equal(first[0].reason, '商品：咖啡');
    await scan();
    assert.equal((await context.request.put('/api/redeem-templates', { headers, data: { templates: [{ ...templates[0], points: 60 }] } })).status(), 200);
    await page.getByRole('button', { name: '確認扣點', exact: true }).click();
    await page.getByRole('status').filter({ hasText: '此筆未扣點' }).waitFor();
    assert.equal(await page.getByRole('heading', { name: '交易結果待確認' }).count(), 0);
    assert.equal((await (await context.request.get('/api/transactions')).json()).length, 1);
    await page.getByRole('button', { name: '咖啡 · 60 點', exact: true }).waitFor();
    assert.deepEqual(errors, []);
    fs.writeFileSync(process.env.TEST_RESULT || 'work/redeem-template-e2e.json', JSON.stringify({ status: 'passed', viewport: '390x844', checks: ['管理員儲存模板', '選商品不立即扣點', '半點商品確認扣點', '交易保留商品名稱', '價格變更拒絕且解除待確認狀態', '載入最新商品價格'], pageErrors: errors }, null, 2));
    console.log('PASS: mobile template editor, confirmation, half points, immutable product name and stale-price recovery');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
