// Every slide of a presentation, for the team's visualiser. Loaded into the
// worker by background.js (importScripts), so it shares its SERVER. While
// present.js says someone is presenting, each tick screenshots the call,
// shrinks it to a THUMB grid and compares it with the last slide sent. A new
// slide goes to renga once the picture has changed and then held still for a
// tick, so a transition or a webcam tile moving doesn't count as a slide.
// Chrome only screenshots the tab in front of its window, and only with the
// "see your tabs" permission; each reason it can't look is said once.
'use strict';

const THUMB = [32, 18];
const CELL = 28;     // how far a cell's brightness (0-255) moves to count as changed
const CHANGED = 0.12; // the share of cells that must change for a new slide

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!sender.tab) return false;
  if (msg.type === 'presenting') presentingChanged(sender.tab, msg.on).catch(() => {});
  if (msg.type === 'slide-tick') slideTick(sender.tab).catch(() => {});
  return false;
});

async function screenAgent() {
  const { team = 'renga' } = await chrome.storage.local.get('team');
  const get = (path) => fetch(SERVER + path).then((r) => (r.ok ? r.json() : Promise.reject()));
  const [rooms, agents] = await Promise.all([get(`/api/rooms?team=${encodeURIComponent(team)}`), get('/api/agents')]);
  const inTeam = new Set(rooms.map((r) => r.id));
  return agents.find((a) => inTeam.has(a.room) && a.senses?.includes('screen')) || null;
}

const post = (path, body) => fetch(SERVER + path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});

async function sayOnce(agent, why, text) {
  const { deck } = await chrome.storage.session.get('deck');
  if (!deck || deck.told?.includes(why)) return;
  await chrome.storage.session.set({ deck: { ...deck, told: [...(deck.told || []), why] } });
  await post('/api/say', { agent_id: agent.id, kind: 'chat', channel: agent.room, text }).catch(() => {});
}

async function presentingChanged(tab, on) {
  const agent = await screenAgent();
  if (!agent) return;
  const { deck } = await chrome.storage.session.get('deck');
  if (on && !deck) {
    await chrome.storage.session.set({ deck: { tabId: tab.id, n: 0, last: null, pending: null, told: [] } });
    await post('/api/say', { agent_id: agent.id, kind: 'chat', channel: agent.room,
      text: "someone's presenting. i'll read every slide." }).catch(() => {});
  } else if (!on && deck) {
    await chrome.storage.session.remove('deck');
    if (deck.n) {
      await post('/api/say', { agent_id: agent.id, kind: 'chat', channel: agent.room,
        text: `the presentation's over: ${deck.n} slide${deck.n === 1 ? '' : 's'} read.` }).catch(() => {});
    }
  }
}

async function slideTick(tab) {
  const { deck } = await chrome.storage.session.get('deck');
  if (!deck || deck.tabId !== tab.id) return;
  const agent = await screenAgent();
  if (!agent) return;
  if (!(await chrome.permissions.contains({ origins: ['<all_urls>'] }))) {
    return sayOnce(agent, 'permission', "i can't see the slides yet: click + then \"read this tab\" "
      + 'in the panel once, and i\'ll read them on my own from then on.');
  }
  if (!(await chrome.tabs.get(tab.id)).active) {
    return sayOnce(agent, 'hidden', "i can only read the slides while the call is the tab on screen.");
  }
  const image = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'jpeg', quality: 70 });
  const thumb = await thumbnail(image);
  const { deck: now } = await chrome.storage.session.get('deck'); // a tick may have raced this one
  if (!now) return;
  if (now.last && !differs(thumb, now.last)) {
    return chrome.storage.session.set({ deck: { ...now, pending: null } }); // still the same slide
  }
  if (!now.pending || differs(thumb, now.pending)) {
    return chrome.storage.session.set({ deck: { ...now, pending: thumb } }); // changing: wait for it to settle
  }
  const n = now.n + 1; // changed, and held still for a tick: a new slide
  await chrome.storage.session.set({ deck: { ...now, n, last: thumb, pending: null } });
  await post('/api/screen', { agent_id: agent.id, url: tab.url, title: tab.title || 'the presentation',
                              text: '', image, slide: n });
}

// The screenshot as a small grid of brightness values, 0-255.
async function thumbnail(dataUrl) {
  const bitmap = await createImageBitmap(await (await fetch(dataUrl)).blob());
  const [w, h] = THUMB;
  const canvas = new OffscreenCanvas(w, h);
  const ctx = canvas.getContext('2d');
  ctx.drawImage(bitmap, 0, 0, w, h);
  const px = ctx.getImageData(0, 0, w, h).data;
  const out = [];
  for (let i = 0; i < px.length; i += 4) out.push(Math.round((px[i] + px[i + 1] + px[i + 2]) / 3));
  return out;
}

function differs(a, b) {
  if (!a || !b || a.length !== b.length) return true;
  let moved = 0;
  for (let i = 0; i < a.length; i++) if (Math.abs(a[i] - b[i]) > CELL) moved++;
  return moved / a.length > CHANGED;
}
