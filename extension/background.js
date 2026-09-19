// The service worker: opens the panel from the toolbar button, and carries
// caption lines from the meet tab to the renga server. Content scripts can't
// reach localhost themselves (the page's CORS applies to them); the worker
// can, because the manifest grants it the host.
'use strict';

const SERVER = 'http://localhost:8020';

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

// What each meet tab's caption reader last reported, so the panel can say
// whether it's actually hearing anything.
const captionState = {};

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.type === 'captions-status' && sender.tab) {
    captionState[sender.tab.id] = msg.status;
    chrome.runtime.sendMessage({ type: 'captions-status', tabId: sender.tab.id, status: msg.status })
      .catch(() => {}); // no panel open: nobody to tell
    return false;
  }
  if (msg.type === 'caption' && sender.tab) {
    fetch(`${SERVER}/api/say`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: 'transcript', kind: 'chat', channel: 'main', text: msg.text }),
    }).then((r) => reply({ ok: r.ok }), () => reply({ ok: false }));
    return true; // reply is async
  }
  if (msg.type === 'get-captions-status') {
    reply({ status: captionState[msg.tabId] || null });
    return false;
  }
  return false;
});

chrome.tabs.onRemoved.addListener((tabId) => { delete captionState[tabId]; });
