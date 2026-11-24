// Renders site/share.jpg, the 1200x630 link-preview card. Needs Node + Playwright:
//   node bird-gallery/scripts/share-card.js
// Change the four Flickr photo ids in `ph` to feature different shots.
const { chromium } = require('playwright'); const fs = require('fs');
const svg = fs.readFileSync(require('path').join(__dirname, '../site/kestrel.svg'), 'utf8');
const base = 'https://live.staticflickr.com/65535/';
const ph = ['55639360732_e4aac5a987', '55162238651_7cf06842b4', '54997682690_164390231f', '55256273008_b0fe155e70'];
const html = `<!doctype html><html><head>
<link href="https://fonts.googleapis.com/css2?family=Jost:ital,wght@0,400;0,500;1,500&display=swap" rel="stylesheet">
<style>
 *{box-sizing:border-box;margin:0}
 body{width:1200px;height:630px;background:#f3eee2;display:grid;grid-template-columns:560px 1fr;font-family:Jost;color:#24261f}
 .l{padding:64px 56px;display:flex;flex-direction:column;justify-content:center}
 .mark{width:132px;height:132px;margin-bottom:34px}
 h1{font:500 72px/1.0 Jost;letter-spacing:-.02em}
 h1 em{color:#3d6b47}
 h1 .dot{color:#a39d89}
 p{margin-top:22px;font-size:24px;line-height:1.4;color:#5f5c4f}
 .r{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;gap:8px;padding:8px 8px 8px 0}
 .r div{background-size:cover;background-position:center;border-radius:6px}
</style></head><body>
 <div class="l"><div class="mark">${svg}</div>
  <h1>Seth Reznik<br><em>Birds</em></h1>
  <p>Bird photography from Brooklyn<br>to Buenos Aires</p></div>
 <div class="r">${ph.map(id => `<div style="background-image:url(${base}${id}_c.jpg)"></div>`).join('')}</div>
</body></html>`;
(async () => { const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1200, height: 630 } });
  await p.setContent(html, { waitUntil: 'networkidle' }); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(800);
  await p.screenshot({ path: require('path').join(__dirname, '../site/share.jpg'), type: 'jpeg', quality: 86 });
  await b.close(); })();
