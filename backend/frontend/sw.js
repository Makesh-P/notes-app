self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", () => self.clients.claim());

self.addEventListener("push", event => {
  if (!event.data) return;

  const data = event.data.json();
  const url = new URL(data.url, self.location.origin).href;

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      badge: "https://cdn-icons-png.flaticon.com/512/1827/1827347.png",
      data: { url }
    })
  );
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const url = event.notification.data.url;

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true })
      .then(clientsArr => {
        for (const client of clientsArr) {
          if (client.url === url && "focus" in client) {
            return client.focus();
          }
        }
        return clients.openWindow(url);
      })
  );
});
