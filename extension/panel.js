// the side panel: one team's chat, narrowed to sit beside whatever you're
// doing. What it reads depends on the team's agents: a screen agent gets a
// button that reads the tab you're on, a captions agent hears meet calls.
// Same event log and api as web/app.js; the layout is what changes.
'use strict';

const SERVER = 'http://localhost:8020';
const hasChrome = typeof chrome !== 'undefined' && chrome.tabs;

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

const state = {
  teams: [], allRooms: [], rooms: [], agents: {}, team: null, room: null, since: 0,
  events: {}, unread: {}, questions: {}, answered: new Set(),
};

// ---- api --------------------------------------------------------------
function setConn(on) {
  $('conn').classList.toggle('on', on);
  $('conn').title = on ? 'connected' : 'renga server offline';
  $('conn').querySelector('.sr').textContent = on ? 'connected' : 'offline';
}

async function api(path, options) {
  let res;
  try {
    res = await fetch(SERVER + path, { headers: { 'Content-Type': 'application/json' }, ...options });
  } catch (err) {
    setConn(false);
    throw new Error(`can't reach renga at ${SERVER}. is the server running?`);
  }
  setConn(true);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) { /* not json */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? null : res.json();
}

function showError(message) {
  $('error').textContent = message || '';
  $('error').hidden = !message;
}

// ---- what this team's agents take in -----------------------------------
// The agent in the current team with a sense, if there is one.
const senser = (sense) => Object.values(state.agents).find(
  (a) => a.senses?.includes(sense) && state.rooms.some((r) => r.id === a.room));

function showListen(status) {
  const who = senser('captions');
  const where = who && `#${room(who.room).name}`;
  const [cls, text] = {
    on: ['on', `listening. meet's captions are going to ${where} as ${who?.name}.`],
    missing: ['warn', `turn on captions in meet (cc button) so ${who?.name} can hear the call.`],
  }[status] || ['', `open a google meet tab and ${who?.name} will listen.`];
  const box = $('listen');
  box.className = 'listen' + (cls ? ' ' + cls : '');
  box.textContent = text;
}

function renderSenses() {
  const hears = senser('captions');
  const sees = senser('screen');
  $('listen').hidden = !hears;
  $('look').hidden = !sees;
  $('deaf').hidden = Boolean(hears || sees);
  if (sees) {
    $('read-screen').textContent = `${sees.name}: read this tab`;
    $('look-note').textContent = `posts to #${room(sees.room).name}`;
  }
  if (hears) checkListen();
}

async function checkListen() {
  if (!senser('captions')) return;
  if (!hasChrome) { showListen(null); return; }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/^https:\/\/meet\.google\.com\/.+/.test(tab.url || '')) { showListen(null); return; }
  const { status } = await chrome.runtime.sendMessage({ type: 'get-captions-status', tabId: tab.id });
  showListen(status || 'missing');
}

if (hasChrome) {
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'captions-status') checkListen();
  });
  chrome.tabs.onActivated.addListener(checkListen);
  chrome.tabs.onUpdated.addListener((_, info) => { if (info.url || info.status === 'complete') checkListen(); });
}

// ---- people and rooms -------------------------------------------------
const room = (id) => state.rooms.find((r) => r.id === id);
const isLead = (id) => state.rooms.some((r) => r.lead === id);

function nameOf(id) {
  if (id === 'admin') return 'you';
  if (id && id.startsWith('room:')) return `#${room(id.slice(5))?.name || id.slice(5)}`;
  return state.agents[id]?.name || id;
}

function avatar(id) {
  const node = el('span', 'av', id === 'admin' ? 'me' : (state.agents[id]?.initials || id.slice(0, 2)));
  if (id === 'admin') node.classList.add('me');
  else if (isLead(id)) node.classList.add('lead');
  node.setAttribute('aria-hidden', 'true');
  return node;
}

const clock = (ts) => new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

function renderRooms() {
  const nav = $('rooms');
  nav.replaceChildren();
  for (const t of state.rooms) {
    const b = el('button', 'room-btn');
    b.type = 'button';
    b.setAttribute('aria-current', String(t.id === state.room));
    b.appendChild(el('span', null, t.name));
    const n = state.unread[t.id] || 0;
    if (n && t.id !== state.room) {
      const c = el('span', 'count', String(n));
      c.setAttribute('aria-label', `${n} new`);
      b.appendChild(c);
    }
    b.addEventListener('click', () => openRoom(t.id));
    nav.appendChild(b);
  }
}

// Whatever the page shows as text. Runs inside the tab, so it can only use
// what's in scope there.
function pageText() {
  return (document.body?.innerText || '').replace(/\n{3,}/g, '\n\n').trim().slice(0, 20000);
}

async function readScreen() {
  const who = senser('screen');
  if (!who) return;
  if (!hasChrome) { showError('reading the screen only works inside the chrome extension.'); return; }
  const btn = $('read-screen');
  btn.disabled = true;
  try {
    // Asked the first time, from the click, so chrome shows its prompt once.
    const granted = await chrome.permissions.request({ origins: ['<all_urls>'] });
    if (!granted) throw new Error('renga needs to see your tabs to read them. click again and allow it.');
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !/^https?:/.test(tab.url || '')) throw new Error("can't read this tab. open a normal web page and try again.");
    $('look-note').textContent = 'reading…';
    const image = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'jpeg', quality: 60 });
    let text = '';
    try {
      const [res] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: pageText });
      text = res?.result || '';
    } catch (_) { /* some pages block scripts; the screenshot still goes */ }
    await api('/api/screen', {
      method: 'POST',
      body: JSON.stringify({ agent_id: who.id, url: tab.url, title: tab.title || '', text, image }),
    });
    showError('');
    if (state.room !== who.room) openRoom(who.room);
    await pollEvents();
  } catch (err) {
    showError(err.message);
  } finally {
    btn.disabled = false;
    $('look-note').textContent = `posts to #${room(who.room).name}`;
  }
}

$('read-screen').addEventListener('click', readScreen);

// ---- which team the panel shows ----------------------------------------
function renderTeamPick() {
  const pick = $('team');
  pick.replaceChildren();
  for (const t of state.teams) {
    const o = el('option', null, t.name);
    o.value = t.id;
    o.selected = t.id === state.team;
    pick.appendChild(o);
  }
  pick.disabled = false;
}

function chooseTeam(id) {
  state.team = id;
  state.rooms = state.allRooms.filter((r) => r.team === id);
  if (hasChrome) chrome.storage.local.set({ team: id }); // the worker reads it for captions
  renderTeamPick();
  renderSenses();
  openRoom(state.rooms[0].id);
}

$('team').addEventListener('change', (e) => chooseTeam(e.target.value));

function openRoom(id) {
  state.room = id;
  state.unread[id] = 0;
  $('c-input').placeholder = `message #${room(id).name}`;
  renderRooms();
  renderLog();
}

// ---- messages ---------------------------------------------------------
const SPOKEN = new Set(['chat', 'question', 'answer', 'handoff', 'task']);

function questionCard(event) {
  const card = el('div', 'card ask');
  card.appendChild(el('div', 'card-label', 'waiting on you'));
  const qid = event.data?.question_id;
  const q = state.questions[qid];
  if (!q || state.answered.has(qid)) {
    card.appendChild(el('div', 'answered', '✓ answered'));
    return card;
  }
  const opts = el('div', 'opts');
  const send = (value) => submitAnswer(q, value, opts);
  if (q.options?.length) {
    for (const o of q.options) {
      const b = el('button', null, o); b.type = 'button';
      b.addEventListener('click', () => send(o));
      opts.appendChild(b);
    }
  } else {
    const field = el('input'); field.type = 'text'; field.placeholder = 'your answer';
    field.setAttribute('aria-label', 'your answer');
    const b = el('button', null, 'answer'); b.type = 'button';
    b.addEventListener('click', () => send(field.value.trim()));
    field.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); send(field.value.trim()); } });
    opts.append(field, b);
  }
  card.appendChild(opts);
  return card;
}

async function submitAnswer(q, value, box) {
  if (!value) return;
  try {
    await api(`/api/questions/${q.id}/answer`, { method: 'POST', body: JSON.stringify({ value }) });
    state.answered.add(q.id);
    box.replaceWith(el('div', 'answered', `✓ ${value}`));
    await pollEvents();
  } catch (err) { showError(err.message); }
}

function statusLine(event) {
  const cls = { announce_done: 'sys done', error: 'sys fail' }[event.kind] || 'sys';
  const row = el('div', cls);
  row.append(el('b', null, nameOf(event.from)),
             document.createTextNode(` ${event.text || event.kind.replace('_', ' ')}`));
  if (!event.data?.frame) return row;
  const wrap = el('div', 'seen');
  const link = el('a', 'shot');
  link.href = event.data.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
  const img = el('img'); img.src = SERVER + event.data.frame;
  img.alt = `screenshot of ${event.data.title || event.data.url}`;
  link.appendChild(img);
  wrap.append(row, link);
  return wrap;
}

function messageRow(event, continues) {
  const row = el('div', 'msg' + (continues ? ' cont' : ''));
  const body = el('div');
  if (!continues) {
    const meta = el('div', 'meta');
    meta.appendChild(el('span', 'who', nameOf(event.from)));
    if (event.to) meta.appendChild(el('span', 'to', `→ ${nameOf(event.to)}`));
    meta.appendChild(el('span', 'time', clock(event.ts)));
    body.appendChild(meta);
  }
  if (event.kind === 'handoff' && room(event.data?.room)) {
    const card = el('div', 'card');
    card.append(el('div', 'card-label', `delegated to ${nameOf('room:' + event.data.room)}`),
                el('div', 'tx', (event.text || '').replace(/^sent to #[\w-]+: /, '')));
    const jump = el('button', 'jump', `open ${room(event.data.room).name} →`); jump.type = 'button';
    jump.addEventListener('click', () => openRoom(event.data.room));
    card.appendChild(jump);
    body.appendChild(card);
  } else if (event.kind === 'task' && event.data?.delegated_from) {
    const card = el('div', 'card');
    card.append(el('div', 'card-label', `brief from ${room(event.data.delegated_from)?.name}`),
                el('div', 'tx', event.text || ''));
    body.appendChild(card);
  } else {
    body.appendChild(el('div', 'tx', event.text || ''));
    if (event.kind === 'question') body.appendChild(questionCard(event));
  }
  row.append(avatar(event.from), body);
  return row;
}

function render(event, prev) {
  if (!SPOKEN.has(event.kind)) return statusLine(event);
  const continues = prev && prev.kind === 'chat' && event.kind === 'chat'
    && prev.from === event.from && prev.to === event.to && event.ts - prev.ts < 120000;
  return messageRow(event, continues);
}

function renderLog() {
  const log = $('log');
  log.replaceChildren();
  const events = state.events[state.room] || [];
  if (!events.length) { log.appendChild(el('div', 'empty', 'nothing said in here yet.')); return; }
  let prev = null;
  for (const e of events) { log.appendChild(render(e, prev)); prev = e; }
  log.scrollTop = log.scrollHeight;
}

function append(event) {
  const list = (state.events[event.channel] ||= []);
  const prev = list[list.length - 1];
  list.push(event);
  if (event.channel !== state.room) {
    state.unread[event.channel] = (state.unread[event.channel] || 0) + 1;
    return true;
  }
  const log = $('log');
  log.querySelector('.empty')?.remove();
  const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 100;
  log.appendChild(render(event, prev));
  if (nearBottom || event.from === 'admin') log.scrollTop = log.scrollHeight;
  return false;
}

async function loadQuestions() {
  const open = await api('/api/questions');
  state.questions = {};
  for (const q of open) state.questions[q.id] = q;
}

async function pollEvents() {
  try {
    const events = await api(`/api/events?since=${state.since}`);
    if (!events.length) return;
    if (events.some((e) => e.data?.question_id && !state.questions[e.data.question_id])) await loadQuestions();
    let elsewhere = false;
    for (const e of events) {
      state.since = Math.max(state.since, e.id);
      elsewhere = append(e) || elsewhere;
    }
    if (elsewhere) renderRooms();
    showError('');
  } catch (err) { showError(err.message); }
}

$('composer').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('c-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  try {
    await api('/api/chat', { method: 'POST', body: JSON.stringify({ text, channel: state.room }) });
    await pollEvents();
  } catch (err) { showError(err.message); input.value = text; }
});

// ---- boot -------------------------------------------------------------
// The server may not be up when the panel opens, so boot keeps retrying
// rather than leaving a dead panel.
async function boot() {
  try {
    const [teams, rooms, agents] = await Promise.all(
      [api('/api/teams'), api('/api/rooms'), api('/api/agents')]);
    state.teams = teams;
    state.allRooms = rooms;
    for (const a of agents) state.agents[a.id] = a;
    await loadQuestions();
    await pollEvents();
    state.unread = {};
    const saved = hasChrome ? (await chrome.storage.local.get('team')).team : null;
    chooseTeam(teams.some((t) => t.id === saved) ? saved : teams[0].id);
    showError('');
    setInterval(pollEvents, 1200);
  } catch (err) {
    showError(err.message);
    setTimeout(boot, 3000);
  }
}

boot();
