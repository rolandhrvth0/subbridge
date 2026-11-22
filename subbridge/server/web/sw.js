// Minimal service worker: makes the page installable and keeps the shell available offline.
const CACHE = "subbridge-v1";
const SHELL = ["/", "/static/app.css", "/static/app.js", "/static/icon.svg",
               "/static/fonts/inter-latin.woff2", "/static/fonts/inter-latin-ext.woff2"];
self.addEventListener("install", e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname === "/ws" || url.pathname.startsWith("/api/")) return;
  // network first, so updates of the desktop app reach the phone immediately
  e.respondWith(fetch(e.request).then(r => {
    const copy = r.clone();
    caches.open(CACHE).then(c => c.put(e.request, copy));
    return r;
  }).catch(() => caches.match(e.request)));
});
