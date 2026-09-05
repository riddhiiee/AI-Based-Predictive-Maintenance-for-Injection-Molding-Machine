/**
 * JS-side mirror of templates/partials/_icons.html, for use when HTML is
 * built dynamically (e.g. assistant chat bubbles, cards rendered from API
 * responses) rather than server-rendered by Jinja.
 */
const Icons = (() => {
  const paths = {
    "alert-triangle": '<path d="M10.3 3.86L1.9 18a2 2 0 0 0 1.7 3h16.8a2 2 0 0 0 1.7-3L13.7 3.86a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13.5"/><circle cx="12" cy="16.5" r="0.5" fill="currentColor"/>',
    "wrench": '<path d="M20 6.5a4.5 4.5 0 0 1-5.9 4.28L6 19a2 2 0 1 1-2.9-2.9l8.2-8.1A4.5 4.5 0 1 1 20 6.5z"/>',
    "zap": '<polygon points="13 2 3 14 11 14 10 22 21 10 13 10 13 2"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><polyline points="8 12.5 11 15.5 16 9"/>',
    "message-square": '<path d="M21 14.5a2 2 0 0 1-2 2H8l-4.5 4V5.5a2 2 0 0 1 2-2H19a2 2 0 0 1 2 2z"/>',
    "file-text": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/>',
    "droplet": '<path d="M12 2.7l5.5 6.1a7.5 7.5 0 1 1-11 0z"/>',
    "flame": '<path d="M8.5 14.5c0 1.66 1.34 3 3 3s3-1.34 3-3c0-1.1-.4-1.6-.8-2.4-.86-1.7-.18-3.24 1.6-4.8.4 2 1.6 3.92 3.2 5.2 1.6 1.28 2.5 2.8 2.5 4.4a7 7 0 1 1-14 0c0-1.5.6-2.8 1.5-3.8v1.4z"/>',
    "network": '<circle cx="12" cy="5" r="2.3"/><circle cx="5" cy="19" r="2.3"/><circle cx="19" cy="19" r="2.3"/><path d="M12 7.3V13M12 13L6.6 17M12 13l5.4 4"/>',
    "book-open": '<path d="M2 4h5.5A3.5 3.5 0 0 1 11 7.5v13A3.5 3.5 0 0 0 7.5 17H2z"/><path d="M22 4h-5.5A3.5 3.5 0 0 0 13 7.5v13a3.5 3.5 0 0 1 3.5-3.5H22z"/>',
    "link": '<circle cx="12" cy="12" r="9"/><path d="M8.5 12h7M12 8.5v7" stroke-opacity="0.001"/><path d="M9.2 14.8a3 3 0 0 1 0-4.24l1.5-1.5a3 3 0 0 1 4.24 4.24l-.86.86"/><path d="M14.8 9.2a3 3 0 0 1 0 4.24l-1.5 1.5a3 3 0 0 1-4.24-4.24l.86-.86"/>',
  };

  function svg(name, cls = "", size = 16) {
    const inner = paths[name] || paths["message-square"];
    return `<svg class="icon ${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;
  }

  return { svg };
})();
