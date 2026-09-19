// renga: rooms where agent teams talk in plain english, and you sit in.
// Plain script, no build step. One log for every room; each room is a
// filtered view of it, and the rooms you're not in count what you missed.
'use strict';

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

const state = {
  teams: [], agents: {}, room: 'main', since: 0, poll: null,
  events: {}, unread: {}, questions: {}, answered: new Set(), last: null,
};

// ---- api --------------------------------------------------------------
function setConn(on) {
  $('conn').classList.toggle('on', on);
  $('conn').title = on ? 'connected' : 'offline';
  $('conn').querySelector('.sr').textContent = on ? 'connected' : 'offline';
}

async function api(path, options) {
  let res;
  try {
    res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  } catch (err) { setConn(false); throw err; }
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

// ---- people -----------------------------------------------------------
const team = (id) => state.teams.find((t) => t.id === id);
const isLead = (id) => state.teams.some((t) => t.lead === id);

function nameOf(id) {
  if (id === 'admin') return 'you';
  if (id && id.startsWith('team:')) return `${team(id.slice(5))?.name || id.slice(5)} team`;
  return state.agents[id]?.name || id;
}

function avatar(id, small) {
  const a = state.agents[id];
  const node = el('span', 'av' + (small ? ' sm' : ''), id === 'admin' ? 'me' : (a?.initials || id.slice(0, 2)));
  if (id === 'admin') node.classList.add('me');
  else if (isLead(id)) node.classList.add('lead');
  node.setAttribute('aria-hidden', 'true');
  return node;
}

const clock = (ts) => new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

// ---- rooms ------------------------------------------------------------
function renderRooms() {
  const nav = $('rooms');
  nav.replaceChildren();
  for (const t of state.teams) {
    const b = el('button', 'room-btn');
    b.type = 'button';
    b.setAttribute('aria-current', String(t.id === state.room));
    b.append(el('span', 'hash', '#'), el('span', null, t.name));
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

function renderMembers() {
  const list = $('members');
  list.replaceChildren();
  for (const a of Object.values(state.agents)) {
    if (a.team !== state.room) continue;
    const li = el('li');
    const text = el('div');
    const name = el('div', 'm-name', a.name);
    if (isLead(a.id)) name.appendChild(el('span', 'lead-mark', 'lead'));
    text.append(name, el('div', 'm-role', a.role));
    li.append(avatar(a.id, true), text);
    list.appendChild(li);
  }
}

function openRoom(id) {
  state.room = id;
  state.unread[id] = 0;
  const t = team(id);
  $('room-name').textContent = t.name;
  $('room-purpose').textContent = t.purpose;
  $('c-input').placeholder = `message #${t.name}`;
  renderRooms();
  renderMembers();
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
  const who = el('b', null, nameOf(event.from));
  row.append(who, document.createTextNode(` ${event.text || event.kind.replace('_', ' ')}`));
  return row;
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

  if (event.kind === 'handoff' && event.data?.team) {
    const card = el('div', 'card');
    card.append(el('div', 'card-label', `delegated to ${nameOf('team:' + event.data.team)}`),
                el('div', 'tx', (event.text || '').replace(/^sent to the \w+ team: /, '')));
    const jump = el('button', 'jump', `open #${team(event.data.team)?.name} →`); jump.type = 'button';
    jump.addEventListener('click', () => openRoom(event.data.team));
    card.appendChild(jump);
    body.appendChild(card);
  } else if (event.kind === 'task' && event.data?.delegated_from) {
    const card = el('div', 'card');
    card.append(el('div', 'card-label', `brief from #${team(event.data.delegated_from)?.name}`),
                el('div', 'tx', event.text || ''));
    body.appendChild(card);
  } else {
    body.appendChild(el('div', 'tx', event.text || ''));
    if (event.kind === 'question') body.appendChild(questionCard(event));
  }

  row.append(avatar(event.from), body);
  return row;
}

function renderLog() {
  const log = $('log');
  log.replaceChildren();
  const events = state.events[state.room] || [];
  if (!events.length) {
    log.appendChild(el('div', 'empty', 'nothing said in here yet.'));
    return;
  }
  let prev = null;
  for (const e of events) {
    log.appendChild(render(e, prev));
    prev = e;
  }
  log.scrollTop = log.scrollHeight;
}

// Consecutive lines from one speaker within two minutes sit under one name.
function render(event, prev) {
  if (!SPOKEN.has(event.kind)) return statusLine(event);
  const continues = prev && SPOKEN.has(prev.kind) && prev.from === event.from
    && prev.to === event.to && event.kind === 'chat' && prev.kind === 'chat'
    && event.ts - prev.ts < 120000;
  return messageRow(event, continues);
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
  const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 120;
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
    if (events.some((e) => e.data?.question_id && !state.questions[e.data.question_id])) {
      await loadQuestions();
    }
    let elsewhere = false;
    for (const e of events) {
      state.since = Math.max(state.since, e.id);
      elsewhere = append(e) || elsewhere;
    }
    if (elsewhere) renderRooms();
  } catch (_) { /* setConn already shows it */ }
}

$('composer').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('c-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  try {
    await api('/api/chat', { method: 'POST', body: JSON.stringify({ text, channel: state.room }) });
    showError('');
    await pollEvents();
  } catch (err) { showError(err.message); input.value = text; }
});

// ---- boot -------------------------------------------------------------
(async () => {
  try {
    const [teams, agents] = await Promise.all([api('/api/teams'), api('/api/agents')]);
    state.teams = teams;
    for (const a of agents) state.agents[a.id] = a;
    await loadQuestions();
    openRoom('main');
    state.since = 0;
    await pollEvents();
    state.unread = {};
    renderRooms();
    state.poll = setInterval(pollEvents, 1200);
  } catch (err) { showError(err.message); }
})();
