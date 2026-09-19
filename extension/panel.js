// the side panel: one team's chat, narrowed to sit beside whatever you're
// doing. Five regions stack down it — header, tabs, live rail, thread,
// composer — and only the thread scrolls (docs/chat-panel.md).
//
// What it reads depends on the team's agents: a captions agent hears meet
// calls and puts the live rail on every tab, a screen agent adds "read this
// tab" to the composer's attach menu. Same event log and api as web/app.js;
// the layout is what changes.
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
  // The call the rail reports on: 'on' while captions are being captured,
  // 'missing' in a meet tab with captions off, null when there's no call.
  call: { status: null, since: 0, marks: 0 },
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

// ---- people and rooms -------------------------------------------------
const room = (id) => state.rooms.find((r) => r.id === id);
const isLead = (id) => state.rooms.some((r) => r.lead === id);

// The agent in the current team with a sense, if there is one.
const senser = (sense) => Object.values(state.agents).find(
  (a) => a.senses?.includes(sense) && state.rooms.some((r) => r.id === a.room));

// Which group a room belongs to, for colour. Provisional: the room that
// hears the call is the research group, everything else designs. The two
// fixed tabs replace this when the panel stops showing n rooms.
const groupOf = (id) => (Object.values(state.agents)
  .some((a) => a.room === id && a.senses?.includes('captions')) ? 'research' : 'design');

function nameOf(id, fallback) {
  if (id === 'admin') return 'you';
  if (fallback && !state.agents[id]) return fallback;
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

function renderTabs() {
  const nav = $('tabs');
  nav.replaceChildren();
  for (const t of state.rooms) {
    const b = el('button', 'tab');
    b.type = 'button';
    b.dataset.group = groupOf(t.id);
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
  // A team with more rooms than the two groups scrolls: keep the one you're
  // in where you can see it.
  nav.querySelector('[aria-current="true"]')?.scrollIntoView({ inline: 'center', block: 'nearest' });
}

// ---- the live rail -----------------------------------------------------
// Is the call being captured, and has anything happened. It renders the same
// on every tab, and leaves the dom entirely when there's no call.
const mmss = (ms) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};

function renderRail() {
  const slot = $('rail-slot');
  const { status } = state.call;
  if (!status) { slot.replaceChildren(); return; }

  const rail = el('button', 'rail' + (status === 'on' ? '' : ' off'));
  rail.type = 'button';
  rail.appendChild(el('span', 'rec'));

  if (status === 'on') {
    const time = el('span', 'elapsed', mmss(Date.now() - state.call.since));
    time.id = 'elapsed';
    rail.appendChild(time);
    const wave = el('span', 'wave');
    wave.setAttribute('aria-hidden', 'true');
    for (let i = 0; i < 28; i++) {
      const bar = el('i');
      bar.style.animationDelay = `${(i % 7) * 0.12}s`;
      wave.appendChild(bar);
    }
    rail.appendChild(wave);
    // A count of findings, not of unread messages, so it doesn't reset when
    // you visit the tab. Nothing emits highlights yet, so it stays hidden.
    if (state.call.marks) rail.appendChild(el('span', 'marks', String(state.call.marks)));
    // The waveform is decorative. Screen readers get the record state and
    // the elapsed time as text instead.
    rail.setAttribute('aria-label',
      `recording, ${mmss(Date.now() - state.call.since)} elapsed. open the call.`);
  } else {
    rail.appendChild(el('span', 'note', `turn on captions (cc) so ${senser('captions')?.name} can hear the call`));
  }

  const home = senser('captions')?.room;
  rail.addEventListener('click', () => {
    if (home && home !== state.room) openRoom(home);
    $('log').scrollTop = $('log').scrollHeight;
  });
  slot.replaceChildren(rail);
}

// Ticks the clock without rebuilding the rail, so the numbers don't jump.
setInterval(() => {
  const time = $('elapsed');
  if (time && state.call.since) time.textContent = mmss(Date.now() - state.call.since);
}, 1000);

function setCall(status) {
  if (status === state.call.status) return;
  if (status === 'on' && !state.call.since) state.call.since = Date.now();
  if (status !== 'on') state.call.since = 0;
  state.call.status = status;
  renderRail();
}

async function checkCall() {
  if (!senser('captions')) { setCall(null); return; }
  if (!hasChrome) { setCall(null); return; }
  // Any meet tab counts, in front or not: the call goes on while you're
  // looking at something else.
  const { status } = await chrome.runtime.sendMessage({ type: 'get-call' });
  setCall(status);
}

if (hasChrome) {
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'captions-status') checkCall();
  });
  chrome.tabs.onUpdated.addListener((_, info) => { if (info.url || info.status === 'complete') checkCall(); });
  chrome.tabs.onRemoved.addListener(checkCall);
}

// ---- the attach menu ---------------------------------------------------
// What paste can't do. Only "this tab" so far, and only for a team with a
// screen agent; github, figma, uploads and call moments come later.
function openMenu(open) {
  $('menu').hidden = !open;
  $('attach').setAttribute('aria-expanded', String(open));
}

function renderAttach() {
  const sees = senser('screen');
  $('attach').hidden = !sees;
  const menu = $('menu');
  menu.replaceChildren();
  if (!sees) { openMenu(false); return; }
  const b = el('button', null, 'this tab');
  b.type = 'button';
  b.setAttribute('role', 'menuitem');
  b.appendChild(el('span', 'note', `to #${room(sees.room).name}`));
  b.addEventListener('click', () => { openMenu(false); readScreen(); });
  menu.appendChild(b);
}

$('attach').addEventListener('click', () => openMenu($('menu').hidden));
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('menu').hidden) { openMenu(false); $('attach').focus(); } });
document.addEventListener('click', (e) => {
  if (!$('menu').hidden && !e.target.closest('#menu, #attach')) openMenu(false);
});

// Whatever the page shows as text. Runs inside the tab, so it can only use
// what's in scope there.
function pageText() {
  return (document.body?.innerText || '').replace(/\n{3,}/g, '\n\n').trim().slice(0, 20000);
}

async function readScreen() {
  const who = senser('screen');
  if (!who) return;
  if (!hasChrome) { showError('reading the screen only works inside the chrome extension.'); return; }
  const btn = $('attach');
  btn.disabled = true;
  try {
    // Asked the first time, from the click, so chrome shows its prompt once.
    const granted = await chrome.permissions.request({ origins: ['<all_urls>'] });
    if (!granted) throw new Error('renga needs to see your tabs to read them. click again and allow it.');
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !/^https?:/.test(tab.url || '')) throw new Error("can't read this tab. open a normal web page and try again.");
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
  }
}

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
  renderAttach();
  checkCall();
  openRoom(state.rooms[0].id);
}

$('team').addEventListener('change', (e) => chooseTeam(e.target.value));

// Opening the panel in an ordinary tab: the whole ui works there, minus the
// chrome apis, and it's the only place the 384px column is real.
if (hasChrome) {
  $('expand').hidden = false;
  $('expand').addEventListener('click', () => chrome.tabs.create({ url: chrome.runtime.getURL('panel.html') }));
}

function openRoom(id) {
  state.room = id;
  state.unread[id] = 0;
  const group = groupOf(id);
  document.body.dataset.group = group;
  // Said twice, here and in send's colour: once the input can carry a
  // codebase, a mis-send is expensive.
  // Named after who is actually in the room, so #logfire doesn't claim design agents.
  const names = Object.values(state.agents).filter((a) => a.room === id).map((a) => a.name);
  const who = names.length > 3 ? `the ${names.length} agents`
    : names.join(' and ').replace(/ and (?=.* and )/g, ', ');
  $('dest').replaceChildren(
    document.createTextNode('goes to '),
    el('b', null, who || 'nobody yet'),
    document.createTextNode(` in #${room(id).name}.`));
  renderTabs();
  renderLog();
}

// ---- messages ---------------------------------------------------------
// A finished piece of work is said in the chat by whoever made it, not a status line.
const SPOKEN = new Set(['chat', 'question', 'answer', 'handoff', 'task', 'announce_done']);

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
  row.append(el('b', null, nameOf(event.from, event.data?.name)),
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

// A message's text, opening with who it's for, the way people write it in a
// group chat: "@project manager can you…". A room is named as #room.
function said(event) {
  const tx = el('div', 'tx');
  if (event.to && event.to !== 'admin') {
    // old hand-offs were addressed to a team:<room>; they read as the room
    const who = event.to.startsWith('team:') ? `#${event.to.slice(5)}` : nameOf(event.to);
    tx.append(el('span', 'mention', who.startsWith('#') ? who : `@${who}`), ' ');
  }
  tx.append(event.text || '');
  return tx;
}

function messageRow(event, continues) {
  const row = el('div', 'msg' + (continues ? ' cont' : ''));
  const body = el('div');
  if (!continues) {
    const meta = el('div', 'meta');
    meta.appendChild(el('span', 'who', nameOf(event.from)));
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
                said(event));
    body.appendChild(card);
  } else {
    body.appendChild(said(event));
    if (event.kind === 'question') body.appendChild(questionCard(event));
    if (event.data?.files?.length) body.appendChild(workFiles(event.data.files));
  }
  row.append(avatar(event.from), body);
  return row;
}

// What an agent made: an svg shows as the image, anything else as a tile to
// open. The files live on the renga server, so their urls get its origin.
function workFiles(files) {
  const grid = el('div', 'work-files');
  for (const f of files) {
    const tile = el('a', 'file');
    tile.href = SERVER + f.url; tile.target = '_blank'; tile.rel = 'noopener noreferrer';
    tile.title = `open ${f.name}`;
    const view = el('div', 'file-view' + (f.type === 'image/svg+xml' ? '' : ' doc'));
    if (f.type === 'image/svg+xml') {
      const img = el('img'); img.src = SERVER + f.url; img.alt = f.name;
      view.appendChild(img);
    } else {
      view.textContent = `.${f.name.split('.').pop()}`;
    }
    tile.append(view, el('div', 'file-name', f.name));
    grid.appendChild(tile);
  }
  return grid;
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
  for (const e of events) {
    const node = render(e, prev);
    node.style.animation = 'none'; // a tab switch isn't agents answering
    log.appendChild(node);
    prev = e;
  }
  log.scrollTop = log.scrollHeight;
}

function append(event, nth = 0) {
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
  const node = render(event, prev);
  node.style.animationDelay = `${Math.min(nth, 4) * 60}ms`;
  log.appendChild(node);
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
    let nth = 0;
    for (const e of events) {
      state.since = Math.max(state.since, e.id);
      elsewhere = append(e, nth++) || elsewhere;
    }
    if (elsewhere) renderTabs();
    showError('');
  } catch (err) { showError(err.message); }
}

// ---- the composer ------------------------------------------------------
// Send stays in a disabled style until there's something to send.
$('c-input').addEventListener('input', (e) => { $('send').disabled = !e.target.value.trim(); });

$('composer').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('c-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  $('send').disabled = true;
  try {
    await api('/api/chat', { method: 'POST', body: JSON.stringify({ text, channel: state.room }) });
    await pollEvents();
  } catch (err) { showError(err.message); input.value = text; $('send').disabled = false; }
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
