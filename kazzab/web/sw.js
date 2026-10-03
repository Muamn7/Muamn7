/*
 * كذّاب — offline shell.
 *
 * Network first, cache as the fallback. A host and its guests must run the
 * same protocol, so a deployed update has to reach every phone on its next
 * load rather than whenever a cache decides to let go. The cache exists so the
 * game against the computer still opens with no connection at all.
 */
const CACHE = 'kazzab-0.1.0';
const SHELL = [
  './', 'index.html', 'manifest.webmanifest', 'css/style.css',
  'js/engine.js', 'js/bot.js', 'js/room.js', 'js/net.js', 'js/audio.js', 'js/app.js',
  'vendor/peerjs.min.js', 'fonts/cairo-arabic.woff2', 'fonts/cairo-latin.woff2',
  'icons/icon-192.png', 'icons/icon-512.png'
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req, { ignoreSearch: true }))
  );
});
