const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const baseURL = process.env.TEST_URL || 'http://localhost:18080';
  const password = process.env.TEST_PASSWORD || 'Only-For-Tests-9284';
  const changed = process.env.TEST_CHANGED_PASSWORD || 'Browser-Changed-9284';
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ baseURL, viewport: { width: 1440, height: 1050 } });
  const errors = [];
  const page = await context.newPage();
  page.on('pageerror', e => errors.push(e.message));
  async function login(target, username, secret) {
    await target.goto(baseURL);
    await target.getByLabel('帳號', { exact: true }).fill(username);
    await target.getByLabel('密碼', { exact: true }).fill(secret);
    await target.getByRole('button', { name: '登入', exact: true }).click();
    await target.getByRole('button', { name: '會員管理', exact: true }).waitFor();
  }
  await login(page, 'test-admin', password);
  async function post(path, data) {
    const identity = await (await context.request.get('/api/auth/me')).json();
    const response = await context.request.post('/api' + path, { headers: { 'X-CSRF-Token': identity.csrf }, data });
    assert.equal(response.status(), 200, await response.text());
    return response.json();
  }
  const suffix = Date.now();
  const member = await post('/users', { member_code: 'FEATURE-' + suffix, display_name: '新版功能測試會員' });
  const body = { idempotency_key: 'features-grant-' + suffix, user_id: member.id, amount: 50, reason: '瀏覽器測試', station_id: 'TEST-PC' };
  await post('/transactions/grant', body);
  await page.getByLabel('QR Token', { exact: true }).fill(member.token);
  await page.getByLabel('QR Token', { exact: true }).press('Enter');
  await page.getByLabel('扣除點數', { exact: true }).waitFor();
  await page.getByRole('button', { name: '確認扣點', exact: true }).click();
  await page.getByRole('status').filter({ hasText: '50 → -50' }).waitFor();
  await page.getByRole('button', { name: '交易紀錄', exact: true }).click();
  const row = page.getByRole('row').filter({ hasText: member.member_code }).filter({ hasText: '扣點' });
  await row.waitFor();
  assert.match(await row.innerText(), /新版功能測試會員/);
  assert.match(await row.innerText(), /test-admin/);
  await page.getByRole('button', { name: '修改密碼', exact: true }).click();
  await page.getByLabel('目前密碼', { exact: true }).fill(password);
  await page.getByLabel('新密碼', { exact: true }).fill(changed);
  await page.getByLabel('確認新密碼', { exact: true }).fill(changed);
  await page.getByRole('button', { name: '儲存新密碼', exact: true }).click();
  await page.getByRole('heading', { name: '操作員登入' }).waitFor();
  await login(page, 'test-admin', changed);
  const staffName = 'browser-staff-' + suffix;
  await post('/operators', { username: staffName, password, role: 'Staff' });
  await page.getByRole('button', { name: '操作員管理', exact: true }).click();
  await page.getByRole('listitem').filter({ hasText: staffName }).getByRole('button', { name: '重設密碼' }).click();
  await page.getByLabel('新密碼', { exact: true }).fill('Staff-Reset-9284');
  await page.getByRole('button', { name: '確認重設', exact: true }).click();
  await page.getByRole('status').filter({ hasText: '員工密碼已重設' }).waitFor();
  const staffContext = await browser.newContext({ baseURL });
  await login(await staffContext.newPage(), staffName, 'Staff-Reset-9284');
  const memberContext = await browser.newContext({ baseURL });
  const portal = await memberContext.newPage();
  portal.on('pageerror', e => errors.push(e.message));
  await portal.goto(baseURL);
  await portal.getByRole('button', { name: '一般使用者查詢', exact: true }).click();
  await portal.getByLabel('會員查詢憑證', { exact: true }).fill(member.token);
  await portal.getByRole('button', { name: '查詢我的點數', exact: true }).click();
  await portal.getByRole('heading', { name: '我的交易紀錄', exact: true }).waitFor();
  assert.match(await portal.locator('.balance').innerText(), /-50/);
  assert.equal((await memberContext.request.get('/api/users')).status(), 401);
  await portal.screenshot({ path: 'docs/ui-v110-member.png', fullPage: true });
  await portal.getByRole('button', { name: '結束查詢並登出', exact: true }).click();
  await portal.getByRole('heading', { name: '掃描自己的會員憑證', exact: true }).waitFor();
  assert.equal((await memberContext.request.get('/api/portal/me')).status(), 401);
  // Feed actual QR pixels through the real ZXing image decoder.
  const png = await (await context.request.get('/api/users/' + member.id + '/qr')).body();
  await portal.getByLabel('辨識 QR 圖片').setInputFiles({ name: 'member.png', mimeType: 'image/png', buffer: png });
  await portal.getByRole('heading', { name: '我的交易紀錄', exact: true }).waitFor();
  // Feed a canvas video stream through getUserMedia, retaining the real camera decoder.
  const cameraContext = await browser.newContext({ baseURL });
  await cameraContext.addInitScript(({ image }) => {
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, value: async () => {
      const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 480;
      const ctx = canvas.getContext('2d'); ctx.fillStyle = 'white'; ctx.fillRect(0, 0, 640, 480);
      const img = new Image(); img.src = image; await img.decode(); ctx.drawImage(img, 160, 80, 320, 320);
      const stream = canvas.captureStream(10); setInterval(() => ctx.drawImage(img, 160, 80, 320, 320), 100); window.testCameraTracks = stream.getTracks(); return stream;
    } });
  }, { image: 'data:image/png;base64,' + png.toString('base64') });
  const cameraPage = await cameraContext.newPage();
  cameraPage.on('pageerror', e => errors.push(e.message));
  await login(cameraPage, 'test-admin', changed);
  await cameraPage.getByRole('button', { name: '開啟相機掃碼', exact: true }).click();
  await cameraPage.getByLabel('扣除點數', { exact: true }).waitFor().catch(async e => { console.log(await cameraPage.locator('body').innerText()); throw e; });
  assert.match(await cameraPage.getByRole('heading').filter({ hasText: member.display_name }).innerText(), /新版功能測試會員/);
  await cameraPage.waitForFunction(() => window.testCameraTracks.every(t => t.readyState === 'ended'));
  // HTTP LAN must show a clear limitation rather than throw or request insecure media.
  const lanURL = process.env.TEST_LAN_URL || 'http://192.168.1.101:18080';
  const lanPage = await (await browser.newContext()).newPage();
  await lanPage.goto(lanURL);
  await lanPage.getByRole('button', { name: '一般使用者查詢', exact: true }).click();
  await lanPage.getByRole('button', { name: '開啟相機掃碼', exact: true }).click();
  await lanPage.getByRole('note').filter({ hasText: '即時相機需要 HTTPS' }).waitFor();
  assert.deepEqual(errors, []);
  const result = { passed: true, features: ['negative redemption', 'transaction names and Chinese labels', 'self password change and relogin', 'staff password reset UI', 'member-only read portal and logout', 'real QR image decoding', 'real camera decoding on simulated video stream', 'camera tracks stopped', 'HTTP LAN camera guidance'], physicalCameraVerified: false };
  fs.writeFileSync('docs/ui-v110-result.json', JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
