// Renders site/share.jpg, the 1200x630 link-preview card. Needs Node + Playwright:
//   node bird-gallery/scripts/share-card.js
// Change the four Flickr photo ids in `ph` to feature different shots.
const { chromium } = require('playwright'); const fs = require('fs');
const svg = fs.readFileSync(require('path').join(__dirname, '../site/kestrel.svg'), 'utf8');
const base = 'https://live.staticflickr.com/65535/';
const ph = ['55639360732_e4aac5a987', '55162238651_7cf06842b4', '54997682690_164390231f', '55256273008_b0fe155e70'];
const html = `<!doctype html><html><head>
<link href="https://fonts.googleapis.com/css2?family=Sorts+Mill+Goudy:ital@0;1&family=Archivo+Narrow:wght@600;700&display=swap" rel="stylesheet">
<style>
 *{box-sizing:border-box;margin:0}
 body{width:1200px;height:630px;display:grid;grid-template-columns:600px 1fr;color:#2e2d29;
   background:#fdfbf6 radial-gradient(ellipse 70% 120% at 0% 115%, #f4e7bf 0%, #f6ebcb 34%, #faf3e0 53%, transparent 53.3%)}
 .l{padding:60px 40px 56px 64px;display:flex;flex-direction:column;justify-content:center;position:relative}
 h1{font:400 112px/.9 "Sorts Mill Goudy";letter-spacing:-.015em;color:#a3262a}
 .sub{margin-top:16px;font:italic 46px/1.05 "Sorts Mill Goudy";color:#7a6a2c}
 .subsub{margin-top:8px;font:italic 26px/1.2 "Sorts Mill Goudy";color:#7a6a2c}
 .ed{margin-top:26px;font:600 15px "Archivo Narrow";letter-spacing:.18em;text-transform:uppercase;color:#8a836d}
 .seal{position:absolute;right:28px;bottom:40px;width:118px;height:118px;padding:5px;border:2px solid #b8953a;border-radius:50%}
 .seal svg{display:block;width:100%;height:100%}
 .r{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;gap:8px;padding:8px 8px 8px 0}
 .r div{background-size:cover;background-position:center;border-radius:4px}
</style></head><body>
 <div class="l">
  <h1>Seth<br>Reznik</h1>
  <p class="sub">Photographs of Birds</p>
  <p class="subsub">from Brooklyn to Buenos Aires</p>
  <p class="ed">Field notes on every species</p>
  <div class="seal">${svg}</div>
 </div>
 <div class="r">${ph.map(id => `<div style="background-image:url(${base}${id}_c.jpg)"></div>`).join('')}</div>
</body></html>`;
(async () => { const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1200, height: 630 } });
  await p.setContent(html, { waitUntil: 'networkidle' }); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(800);
  await p.screenshot({ path: require('path').join(__dirname, '../site/share.jpg'), type: 'jpeg', quality: 86 });
  await b.close(); })();
