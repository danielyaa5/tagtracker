// Recreate public media using the real dashboard and temporary fictional data.
const {chromium} = require('playwright');
const {spawn, execFileSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const ROOT = path.resolve(__dirname, '..');
const ASSETS = path.join(ROOT, 'site/assets');
const FFMPEG = process.env.FFMPEG || 'ffmpeg';

function launchOptions() {
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE) {
    return {headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE};
  }
  return {headless: true};
}

async function stopServer(server) {
  if (server.exitCode !== null || server.signalCode !== null) return;
  await new Promise(resolve => {
    server.once('exit', resolve);
    server.kill('SIGINT');
  });
}

async function main() {
  try {
    execFileSync(FFMPEG, ['-version'], {stdio: 'ignore'});
  } catch {
    throw Error('ffmpeg is required. Install it and ensure it is on PATH (or set FFMPEG).');
  }
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tagtracker-media-'));
  const output = path.join(temporary, 'output');
  fs.mkdirSync(output);
  let browser;
  let context;
  const server = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, 'demo_server.py'), '--port', '0'], {cwd: ROOT});
  server.stderr.on('data', data => process.stderr.write(data));
  try {
    const url = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(Error('Demo server did not start within 20 seconds.')), 20000);
      server.stdout.once('data', data => {clearTimeout(timeout); resolve(data.toString().trim());});
      server.once('error', error => {clearTimeout(timeout); reject(error);});
      server.once('exit', code => {clearTimeout(timeout); reject(Error('Demo server exited: ' + code));});
    });
    browser = await chromium.launch(launchOptions());
    const viewport = {width: 1200, height: 1080};
    context = await browser.newContext({viewport, deviceScaleFactor: 1, timezoneId: 'America/Los_Angeles'});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const clips = {history: [], map: []};
    async function frame(clip, seconds) {
      const frames = clips[clip];
      const file = path.join(temporary, `${clip}-${frames.length}.png`);
      await page.screenshot({path: file});
      frames.push({file, seconds});
    }
    async function focusHistory() {
      await page.evaluate(() => window.scrollTo({top: document.querySelector('h2').offsetTop - 24, behavior: 'instant'}));
    }
    async function tiles() {
      await page.waitForFunction(() => document.querySelectorAll('img.leaflet-tile').length > 0 && [...document.querySelectorAll('img.leaflet-tile')].every(img => img.complete && img.naturalWidth > 0), null, {timeout: 30000});
      await page.waitForTimeout(300);
    }
    async function loaded(count) {
      await page.waitForFunction(expected => document.querySelector('#map-status').textContent.startsWith(expected + ' observations'), count);
      await tiles();
    }
    await page.goto(url);
    const icon = await page.locator('link[rel="icon"]').getAttribute('href');
    const iconResponse = await page.request.get(new URL(icon, url).href);
    if (!iconResponse.ok() || !iconResponse.headers()['content-type'].includes('image/svg+xml')) throw Error('Dashboard tab icon did not load.');
    await page.getByRole('link', {name: 'Demo backpack', exact: true}).waitFor();
    if (!(await page.locator('body').innerText()).includes('3 items · 2 devices')) throw Error('Demo fixture did not produce the expected item and device counts.');
    await page.screenshot({path: path.join(output, 'overview.png'), fullPage: true});
    await page.setViewportSize({width: 1200, height: 800});
    await frame('history', 1.2);
    await page.getByRole('link', {name: 'Demo backpack', exact: true}).click();
    await loaded(4);
    await focusHistory();
    await frame('history', 1.8);
    await page.selectOption('#range', '7d');
    await loaded(8);
    await frame('history', 1.8);
    await page.selectOption('#range', 'all');
    await loaded(10);
    await frame('history', 1.8);
    await frame('map', .8);
    await page.getByLabel('Connect lines').check();
    await page.waitForFunction(() => document.querySelector('path[stroke-dasharray]'));
    await page.screenshot({path: path.join(output, 'history.png'), fullPage: true});
    await frame('map', 1.6);
    await page.locator('.leaflet-interactive[fill="#3889e8"]').first().click();
    await page.locator('.leaflet-popup').waitFor();
    await frame('map', 2);
    await page.locator('.leaflet-popup-close-button').click();
    await page.getByRole('button', {name: 'Fit all points'}).click();
    await tiles();
    await frame('map', 1.6);
    await page.getByRole('link', {name: '← Back to all items'}).click();
    await page.getByRole('link', {name: 'Demo phone', exact: true}).click();
    await loaded(3);
    await page.selectOption('#range', 'all');
    await loaded(5);
    await page.screenshot({path: path.join(output, 'devices.png'), fullPage: true});
    await page.getByRole('link', {name: '← Back to all items'}).click();
    await page.getByRole('link', {name: 'Demo backpack', exact: true}).waitFor();
    if (errors.length) throw Error(errors.join('\n'));
    await context.close();
    context = null;
    await browser.close();
    browser = null;
    for (const [clip, frames] of Object.entries(clips)) {
      const list = path.join(temporary, `${clip}.txt`);
      fs.writeFileSync(list, frames.map(frame => `file '${frame.file}'\nduration ${frame.seconds}\n`).join('') + `file '${frames.at(-1).file}'\n`);
      const duration = frames.reduce((total, frame) => total + frame.seconds, 0);
      execFileSync(FFMPEG, ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', list, '-t', String(duration), '-filter_complex', 'fps=5,scale=1000:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4', '-loop', '0', path.join(output, `${clip}-demo.gif`)]);
      fs.copyFileSync(frames[1].file, path.join(output, `${clip}-demo.png`));
    }
    fs.mkdirSync(ASSETS, {recursive: true});
    for (const name of fs.readdirSync(output)) fs.copyFileSync(path.join(output, name), path.join(ASSETS, name));
    for (const name of ['demo.gif', 'demo.mp4']) fs.rmSync(path.join(ASSETS, name), {force: true});
    console.log('Created overview.png, history.png, devices.png, and two short GIFs with still posters: history-demo and map-demo.');
    console.log('Verified: item/device history, date filters, timeline lines, pin popup, and fit controls.');
    console.log('All data is fictional. Browser and temporary server are closed after capture.');
  } finally {
    if (context) await context.close();
    if (browser) await browser.close();
    await stopServer(server);
    fs.rmSync(temporary, {recursive: true, force: true});
  }
}
main().catch(error => {console.error(error.message); process.exitCode = 1;});
