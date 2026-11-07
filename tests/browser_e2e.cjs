// Run against a disposable test database with an initialized test-admin account.
// TEST_PASSWORD is exclusively test data. No production credentials in this file.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ baseURL: process.env.TEST_URL || 'http://127.0.0.1:18080', viewport: { width: 1440, height: 1050 } });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('pageerror', e => consoleErrors.push(e.message));
  await page.goto(process.env.TEST_URL || 'http://127.0.0.1:18080');
  const environment = await page.evaluate(() => ({ secureContext: window.isSecureContext, randomUUID: typeof crypto.randomUUID }));
  if (process.env.TEST_EXPECT_LAN === '1') {
    assert.equal(environment.secureContext, false);
    assert.equal(environment.randomUUID, 'undefined');
  }
  await page.getByLabel('帳號', { exact: true }).fill('test-admin');
  await page.getByLabel('密碼', { exact: true }).fill(process.env.TEST_PASSWORD || 'Only-For-Tests-9284');
  await page.getByRole('button', { name: '登入', exact: true }).click();
  await page.getByRole('button', { name: '會員管理', exact: true }).waitFor();
  const session = await context.request.get('/api/auth/me');
  const identity = await session.json();
  const post = async (path, data) => {
    const r = await context.request.post('/api' + path, { headers: { 'X-CSRF-Token': identity.csrf }, data });
    assert.equal(r.status(), 200, await r.text());
    return r.json();
  };
  await page.getByRole('button', { name: '會員管理', exact: true }).click();
  const code = 'BROWSER-' + Date.now();
  await page.getByLabel('會員編號', { exact: true }).fill(code);
  await page.getByLabel('顯示名稱', { exact: true }).fill('瀏覽器測試會員');
  await page.getByRole('button', { name: '建立會員', exact: true }).click();
  const row = page.getByRole('row').filter({ hasText: code });
  await row.waitFor();
  await row.getByRole('button', { name: 'QR', exact: true }).click();
  await page.getByAltText('會員 QR 憑證').waitFor();
  assert.equal(await page.getByAltText('會員 QR 憑證').evaluate(img => new Promise(resolve => { if (img.complete) resolve(img.naturalWidth > 0); else img.onload = () => resolve(img.naturalWidth > 0); })), true);
  await page.getByRole('button', { name: '關閉', exact: true }).click();
  await row.getByRole('button', { name: '發點 / 調整', exact: true }).click();
  await page.getByLabel('發放點數', { exact: true }).fill('500');
  await page.getByRole('button', { name: '確認發點', exact: true }).click();
  await page.getByRole('status').filter({ hasText: '交易成功' }).waitFor();
  const member = (await (await context.request.get('/api/users?q=' + code)).json())[0];
  assert.equal(member.balance, 500);
  const qr = await post('/users/' + member.id + '/qr/reissue');
  await page.getByRole('button', { name: '掃碼核銷', exact: true }).click();
  await page.getByLabel('QR Token', { exact: true }).fill(qr.token);
  await page.getByLabel('QR Token', { exact: true }).press('Enter');
  await page.getByLabel('扣除點數', { exact: true }).waitFor();
  await page.screenshot({ path: process.env.SCREENSHOT || 'docs/browser-scan.png', fullPage: true });
  await page.getByRole('button', { name: '確認扣點', exact: true }).click();
  await page.getByRole('status').filter({ hasText: '500 → 400' }).waitFor();
  assert.equal((await (await context.request.get('/api/users/' + member.id)).json()).balance, 400);
  // A disconnected station cannot claim success; pending key is preserved.
  await page.getByLabel('QR Token', { exact: true }).fill(qr.token);
  await page.getByLabel('QR Token', { exact: true }).press('Enter');
  await page.getByLabel('扣除點數', { exact: true }).waitFor();
  await context.setOffline(true);
  await page.getByRole('button', { name: '確認扣點', exact: true }).click();
  await page.getByRole('heading', { name: '交易結果待確認' }).waitFor();
  await page.getByRole('status').filter({ hasText: '結果待確認' }).waitFor();
  assert.match(await page.getByRole('status').innerText(), /結果待確認/);
  await context.setOffline(false);
  await page.getByRole('button', { name: '以原鍵重試', exact: true }).click();
  await page.getByRole('status').filter({ hasText: '交易已確認' }).waitFor();
  assert.equal((await (await context.request.get('/api/users/' + member.id)).json()).balance, 300);
  // Retry/recovery must not leave a second transaction for the same key.
  const txs = await (await context.request.get('/api/transactions?user_id=' + member.id)).json();
  assert.deepEqual(txs.map(t => t.delta).sort((a, b) => a-b), [-100, -100, 500]);
  await page.getByRole('button', { name: '交易紀錄', exact: true }).click();
  await page.getByRole('columnheader', { name: '前 → 後', exact: true }).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '掃碼核銷', exact: true }).click();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  assert.deepEqual(consoleErrors, []);
  const result = { passed: true, environment, url: process.env.TEST_URL || 'http://127.0.0.1:18080', browser: await browser.version(), assertions: ['login', 'create member', 'QR image', 'grant 500', 'HID Enter lookup', 'redeem 100 => 400', 'offline pending without success', 'original-key retry => 300', 'ledger reconciled', 'mobile viewport', 'no browser script errors'] };
  fs.writeFileSync('docs/browser-e2e-result.json', JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
