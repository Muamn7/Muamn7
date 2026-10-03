/*
 * Serves the game from web/ for development, and optionally a PeerJS broker
 * next to it.
 *
 *   node tools/serve.js                 game on http://localhost:8080
 *   node tools/serve.js --peer          plus a broker on :9000 - open
 *                                       http://<this computer's IP>:8080/?peer=<IP>:9000&ice=none
 *                                       on phones on the same Wi-Fi to play
 *                                       with no internet at all
 */
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', 'web');
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.webmanifest': 'application/manifest+json',
  '.json': 'application/json', '.txt': 'text/plain; charset=utf-8'
};

function staticServer() {
  return http.createServer((req, res) => {
    let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    if (p.endsWith('/')) p += 'index.html';
    const file = path.normalize(path.join(ROOT, p));
    if (!file.startsWith(ROOT)) { res.writeHead(403); res.end(); return; }
    fs.readFile(file, (err, data) => {
      if (err) { res.writeHead(404); res.end('not found'); return; }
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
      res.end(data);
    });
  });
}

/** host defaults to every IPv4 interface: peer's own default is '::', which fails where IPv6 is off. */
function startPeer(port, host) {
  const { PeerServer } = require('peer');
  return new Promise((resolve) => {
    const s = PeerServer({ port, host: host || '0.0.0.0', path: '/', allow_discovery: false }, () => resolve(s));
  });
}

module.exports = { staticServer, startPeer };

if (require.main === module) {
  const port = Number(process.env.PORT || 8080);
  staticServer().listen(port, () => console.log(`كذّاب: http://localhost:${port}/`));
  if (process.argv.includes('--peer')) {
    startPeer(9000).then(() => console.log('PeerJS broker on :9000 — add ?peer=<this-ip>:9000&ice=none to the URL'));
  }
}
