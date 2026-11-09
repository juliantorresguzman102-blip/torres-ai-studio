const CACHE = 'torres-ai-studio-v3';
self.addEventListener('install', event => { event.waitUntil(self.skipWaiting()); });
self.addEventListener('activate', event => {
  event.waitUntil(Promise.all([
    caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('torres-ai-') && k !== CACHE).map(k => caches.delete(k)))),
    self.clients.claim()
  ]));
});
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || new URL(event.request.url).origin !== self.location.origin) return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
