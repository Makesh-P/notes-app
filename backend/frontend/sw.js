self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", () => {
  self.clients.claim();
});

self.addEventListener("notificationclick", event => {
  event.notification.close();

  const noteId = event.notification.data.noteId;
  const url = `note.html?id=${noteId}`;

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true })
      .then(clientList => {
        for (const client of clientList) {
          if (client.url.includes("note.html")) {
            return client.focus();
          }
        }
        return clients.openWindow(url);
      })
  );
});
