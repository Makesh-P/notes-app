self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", () => {
  self.clients.claim();
});

// 1. Listen for Push Messages from Server
self.addEventListener('push', function(event) {
  if (event.data) {
    const data = event.data.json();
    const options = {
      body: data.body,
      // Removed icon requirement for testing; add a real URL later
      badge: 'https://cdn-icons-png.flaticon.com/512/1827/1827347.png', 
      data: {
        url: data.url.startsWith('http') ? data.url : self.location.origin + data.url
      }
    };

    event.waitUntil(
      self.registration.showNotification(data.title, options)
    );
  }
});

// 2. Handle Click (Open the Note)
self.addEventListener("notificationclick", event => {
  event.notification.close();
  const url = event.notification.data.url;

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true })
      .then(clientList => {
        // If tab is open, focus it
        for (const client of clientList) {
          if (client.url.includes(url)) {
            return client.focus();
          }
        }
        // If not, open new window
        return clients.openWindow(url);
      })
  );
});