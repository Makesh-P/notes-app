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
      icon: '/icon.png', // Add an icon.png to your folder if you want
      data: {
        url: data.url
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