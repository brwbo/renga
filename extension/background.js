// The service worker: opens the panel from the toolbar button, and carries
// caption lines from the meet tab to the renga server, as the captions agent
// of whichever team the panel shows. A team without one hears nothing. Content scripts can't
// reach localhost themselves (the page's CORS applies to them); the worker
// can, because the manifest grants it the host.
'use strict';

const SERVER = 'http://localhost:8020';

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

// What each meet tab's caption reader last reported, so the panel can say
// whether it's actually hearing anything. Kept in session storage: chrome
// stops this worker whenever the call goes quiet for half a minute, and a
// plain object would forget the call was on.
const MEETING = /^https:\/\/meet\.google\.com\/.+/;
async function captionState() {
  const { calls = {} } = await chrome.storage.session.get('calls');
  return calls;
}
async function setCaptionState(tabId, status) {
  const calls = await captionState();
  if (status) calls[tabId] = status; else delete calls[tabId];
  await chrome.storage.session.set({ calls });
}

// The call the panel reports on: any meet tab hearing captions, or else one
// with them off. You can be in another tab while the call goes on.
async function callStatus() {
  const calls = await captionState();
  const tabs = await chrome.tabs.query({ url: 'https://meet.google.com/*' });
  const live = tabs.filter((t) => MEETING.test(t.url || '')).map((t) => calls[t.id]).filter(Boolean);
  return live.includes('on') ? 'on' : (live.length ? 'missing' : null);
}

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
    setCaptionState(sender.tab.id, msg.status).then(() =>
      chrome.runtime.sendMessage({ type: 'captions-status', tabId: sender.tab.id, status: msg.status }))
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
      }).then(async (r) => {
        reply({ ok: r.ok });
        const said = r.ok ? await r.json() : null;
        if (said?.look) lookAtCall(sender.tab.id, said.look);
      });
    }).catch(() => reply({ ok: false }));
    return true; // reply is async
  }
  if (msg.type === 'get-call') {
    callStatus().then((status) => reply({ status }), () => reply({ status: null }));
    return true;
  }
  return false;
});

// ---- looking when someone shows something ------------------------------
// The server flags a caption line like "as you can see" with `look`: which
// screen agent should look, and the words that asked. Chrome only lets us
// capture the tab in front of its window, so it's the call only while the
// call is on screen. Each reason not to look is said once per session, not
// on every cue.
async function lookAtCall(tabId, look) {
  const say = async (why, text) => {
    const { told = {} } = await chrome.storage.session.get('told');
    if (told[why]) return;
    await chrome.storage.session.set({ told: { ...told, [why]: true } });
    await fetch(`${SERVER}/api/say`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: look.agent_id, kind: 'chat', channel: look.room, text }),
    }).catch(() => {});
  };
  try {
    if (!(await chrome.permissions.contains({ origins: ['<all_urls>'] }))) {
      return say('permission', `someone's showing something ("${look.because}"), but i can't see your tabs yet. `
        + 'click + then "read this tab" in the panel once, and i\'ll look on my own from then on.');
    }
    const tab = await chrome.tabs.get(tabId);
    if (!tab.active) {
      return say('hidden', `missed it ("${look.because}"): the call wasn't the tab on screen. `
        + 'i can only look at the call while it is.');
    }
    const image = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'jpeg', quality: 60 });
    await fetch(`${SERVER}/api/screen`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: look.agent_id, url: tab.url, title: tab.title || 'the call',
                             text: '', image, because: look.because }),
    });
  } catch (_) { /* the window is minimised, or the tab went away: nothing to see */ }
}

chrome.tabs.onRemoved.addListener((tabId) => { setCaptionState(tabId, null); });
chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (info.url && !MEETING.test(info.url)) setCaptionState(tabId, null); // left the call
});
