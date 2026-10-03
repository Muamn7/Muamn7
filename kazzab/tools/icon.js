/*
 * Renders tools/icon.html to the web app icons and the Android launcher icons.
 *   node tools/icon.js        (needs the devDependencies: npm install)
 */
'use strict';
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
  const page = await browser.newPage({ viewport: { width: 512, height: 512 } });
  await page.goto('file://' + path.join(__dirname, 'icon.html'));
  await page.evaluate(() => document.fonts.ready);
  const root = path.join(__dirname, '..');
  const out = [
    ['web/icons/icon-512.png', 512], ['web/icons/icon-maskable-512.png', 512], ['web/icons/icon-192.png', 192],
    ['android/app/src/main/res/mipmap-mdpi/ic_launcher.png', 48],
    ['android/app/src/main/res/mipmap-hdpi/ic_launcher.png', 72],
    ['android/app/src/main/res/mipmap-xhdpi/ic_launcher.png', 96],
    ['android/app/src/main/res/mipmap-xxhdpi/ic_launcher.png', 144],
    ['android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png', 192]
  ];
  const full = await page.locator('#icon').screenshot();
  const tmp = path.join(require('os').tmpdir(), 'kazzab-icon.png');
  fs.writeFileSync(tmp, full);
  for (const [file, size] of out) {
    const p = await browser.newPage({ viewport: { width: size, height: size } });
    await p.setContent(`<body style="margin:0"><img src="data:image/png;base64,${full.toString('base64')}" style="width:${size}px;height:${size}px;display:block"></body>`);
    await p.screenshot({ path: path.join(root, file) });
    await p.close();
  }
  await browser.close();
  console.log('icons written');
})();
