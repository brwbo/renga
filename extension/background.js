// The service worker: opens the panel from the toolbar button, and carries
// caption lines from the meet tab to the renga server, as the captions agent
// of whichever team the panel shows. A team without one hears nothing. Content scripts can't
// reach localhost themselves (the page's CORS applies to them); the worker
// can, because the manifest grants it the host.
'use strict';

const SERVER = 'http://localhost:8020';

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

// What each meet tab's caption reader last reported, so the panel can say
// whether it's actually hearing anything.
const captionState = {};

// The team's captions agent, looked up again at most every ten seconds so a
// team switch in the panel takes effect without reloading the extension.
let cached = { at: 0, team: null, agent: null };
async function captionAgent() {
  const { team = 'renga' } = await chrome.storage.local.get('team');
  if (team === cached.team && Date.now() - cached.at < 10000) return cached.agent;
  const get = (path) => fetch(SERVER + path).then((r) => (r.ok ? r.json() : Promise.reject()));
  const [rooms, agents] = await Promise.all([get(`/api/rooms?team=${encodeURIComponent(team)}`), get('/api/agents')]);
  const inTeam = new Set(rooms.map((r) => r.id));
  const agent = agents.find((a) => inTeam.has(a.room) && a.senses?.includes('captions')) || null;
  cached = { at: Date.now(), team, agent };
  return agent;
}

chrome.storage.onChanged.addListener((changes) => { if (changes.team) cached.at = 0; });

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.type === 'captions-status' && sender.tab) {
    captionState[sender.tab.id] = msg.status;
    chrome.runtime.sendMessage({ type: 'captions-status', tabId: sender.tab.id, status: msg.status })
      .catch(() => {}); // no panel open: nobody to tell
    return false;
  }
  if (msg.type === 'caption' && sender.tab) {
    captionAgent().then((agent) => {
      if (!agent) return reply({ ok: false, reason: 'no captions agent in this team' });
      return fetch(`${SERVER}/api/say`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agent.id, kind: 'chat', channel: agent.room, text: msg.text }),
      }).then((r) => reply({ ok: r.ok }));
    }).catch(() => reply({ ok: false }));
    return true; // reply is async
  }
  if (msg.type === 'get-captions-status') {
    reply({ status: captionState[msg.tabId] || null });
    return false;
  }
  return false;
});

chrome.tabs.onRemoved.addListener((tabId) => { delete captionState[tabId]; });
