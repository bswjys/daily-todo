/* 데일리 투두 · 오프라인 캐시
 *  - 화면(index.html), 코드(app.js, styles.css): 네트워크 우선 → 실패하면 캐시
 *  - 아이콘·manifest 등: 캐시 우선
 */
const CACHE = 'daily-todo-v3';
const VERSION = '3';
const ASSETS = [
  './',
  './index.html',
  './styles.css?v=' + VERSION,
  './app.js?v=' + VERSION,
  './styles.css',
  './app.js',
  './manifest.webmanifest',
  './icon-180.png',
  './icon-192.png',
  './icon-512.png',
  './apple-touch-icon.png'
];

const isCode = (path) => /\/app\.js$/.test(path) || /\/styles\.css$/.test(path);

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => Promise.all(ASSETS.map((url) => cache.add(url).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k.startsWith('daily-todo-') && k !== CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

function networkFirst(req, cacheKey) {
  return fetch(req, { cache: 'no-cache' })
    .then((res) => {
      if (res && res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then((cache) => cache.put(cacheKey, copy)).catch(() => {});
      }
      return res;
    })
    .catch(() => caches.match(cacheKey, { ignoreSearch: true })
      .then((hit) => hit || caches.match(req)));
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (req.mode === 'navigate') {
    event.respondWith(networkFirst(req, './index.html'));
    return;
  }

  if (isCode(url.pathname)) {
    const key = /\/app\.js$/.test(url.pathname) ? './app.js' : './styles.css';
    event.respondWith(networkFirst(req, key));
    return;
  }

  event.respondWith(
    caches.match(req, { ignoreSearch: true }).then((hit) => {
      if (hit) return hit;
      return fetch(req).then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy)).catch(() => {});
        }
        return res;
      });
    })
  );
});
