// renga: teams of agents, one per repo, talking in plain english in their
// rooms while you sit in. Plain script, no build step. One log for every
// room; each room is a filtered view of it, and the rooms you're not in
// count what you missed. #/ is the teams page, #/room/<id> is a room.
'use strict';

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

const state = {
  teams: [], rooms: [], agents: {}, room: null, since: 0, poll: null,
  events: {}, unread: {}, questions: {}, answered: new Set(), last: null,
  logfire: null,  // the logfire project a trace id links into, when there is one
};

// ---- api --------------------------------------------------------------
function setConn(on) {
  for (const c of document.querySelectorAll('.conn')) {
    c.classList.toggle('on', on);
    c.title = on ? 'connected' : 'offline';
    c.querySelector('.sr').textContent = on ? 'connected' : 'offline';
  }
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
    // fastapi's 422s are a list of {loc, msg}; say them as "field: problem".
    if (Array.isArray(detail)) {
      detail = detail.map((d) => `${d.loc?.at(-1)}: ${String(d.msg).replace(/^value error, /i, '')}`).join('; ');
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? null : res.json();
}

function showError(message) {
  for (const id of ['error', 'home-error', 'library-error']) {
    $(id).textContent = message || '';
    $(id).hidden = !message;
  }
}

// ---- people -----------------------------------------------------------
const team = (id) => state.teams.find((t) => t.id === id);
const room = (id) => state.rooms.find((r) => r.id === id);
const roomsOf = (teamId) => state.rooms.filter((r) => r.team === teamId);
const isLead = (id) => state.rooms.some((r) => r.lead === id);
// Which group a room belongs to, for colour: the same rule as the side
// panel. The room with an agent that hears the call is research; every
// other room designs.
const groupOf = (roomId) => (Object.values(state.agents)
  .some((a) => a.room === roomId && a.senses?.includes('captions')) ? 'research' : 'design');

function nameOf(id, fallback) {
  if (id === 'admin') return 'you';
  if (fallback && !state.agents[id]) return fallback;
  if (id && id.startsWith('room:')) return `#${room(id.slice(5))?.name || id.slice(5)}`;
  return state.agents[id]?.name || id;
}

function avatar(id, small) {
  const a = state.agents[id];
  const initials = id === 'admin' ? 'me' : (a?.initials || id.slice(0, 2));
  const node = el('span', 'av' + (small ? ' sm' : ''));
  if (id === 'admin') node.classList.add('me');
  else if (isLead(id)) node.classList.add('lead');
  node.setAttribute('aria-hidden', 'true');

  if (a?.avatar_url) {
    const img = el('img', 'av-img');
    img.src = a.avatar_url;
    img.alt = '';
    img.onerror = () => {
      img.remove();
      node.textContent = initials;
    };
    node.appendChild(img);
  } else {
    node.textContent = initials;
  }
  return node;
}

const clock = (ts) => new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

const repoUrl = (repo) => `https://github.com/${repo}`;

function unreadBadge(n) {
  const c = el('span', 'count', String(n));
  c.setAttribute('aria-label', `${n} new`);
  return c;
}

// ---- teams page -------------------------------------------------------
function lastLine(roomId) {
  const events = state.events[roomId] || [];
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].text) return events[i];
  }
  return null;
}

function renderHome() {
  const grid = $('teams');
  grid.replaceChildren();
  for (const t of state.teams) {
    const card = el('section', 'team-card');
    card.setAttribute('aria-labelledby', `team-${t.id}`);
    const head = el('div', 'team-card-head');
    const h = el('h2', null, t.name); h.id = `team-${t.id}`;
    const repo = el('a', 'repo', t.repo);
    repo.href = repoUrl(t.repo); repo.target = '_blank'; repo.rel = 'noopener';
    const del = el('button', 'del', 'delete');
    del.type = 'button';
    del.setAttribute('aria-label', `delete the ${t.name} team`);
    del.addEventListener('click', () => confirmDelete(card, `delete ${t.name}? its rooms and agents go too.`,
      () => deleteTeam(t.id)));
    head.append(h, repo, del);
    card.append(head, el('p', 'team-purpose', t.purpose));

    const list = el('div', 'team-rooms');
    for (const r of roomsOf(t.id)) {
      const link = el('a', 'team-room');
      link.href = `#/room/${r.id}`;
      const top = el('div', 'tr-top');
      top.append(el('span', 'hash', '#'), el('span', 'tr-name', r.name));
      const members = Object.values(state.agents).filter((a) => a.room === r.id);
      top.appendChild(el('span', 'tr-count', members.length ? `${members.length} agents` : 'empty'));
      if (state.unread[r.id]) top.appendChild(unreadBadge(state.unread[r.id]));
      const last = lastLine(r.id);
      const preview = el('div', 'tr-last', last ? `${nameOf(last.from)}: ${last.text}` : r.purpose);
      link.append(top, preview);
      list.appendChild(link);
    }
    card.appendChild(list);
    grid.appendChild(card);
  }
}

// ---- deleting -----------------------------------------------------------
// Every delete asks first, in place: the thing turns into a yes/no line.
function confirmDelete(host, question, onYes) {
  host.querySelector('.confirm')?.remove();
  const box = el('div', 'confirm');
  box.setAttribute('role', 'alertdialog');
  box.setAttribute('aria-label', question);
  const yes = el('button', 'btn danger', 'delete'); yes.type = 'button';
  const no = el('button', 'btn ghost', 'cancel'); no.type = 'button';
  const msg = el('p', 'confirm-q', question);
  const err = el('p', 'form-err'); err.hidden = true;
  no.addEventListener('click', () => box.remove());
  yes.addEventListener('click', async () => {
    yes.disabled = true;
    try { await onYes(); } catch (e) { err.textContent = e.message; err.hidden = false; yes.disabled = false; }
  });
  box.append(msg, el('div', 'form-actions'), err);
  box.querySelector('.form-actions').append(yes, no);
  host.appendChild(box);
  no.focus();
}

async function deleteTeam(id) {
  await api(`/api/teams/${id}`, { method: 'DELETE' });
  const rooms = new Set(roomsOf(id).map((r) => r.id));
  state.teams = state.teams.filter((t) => t.id !== id);
  state.rooms = state.rooms.filter((r) => !rooms.has(r.id));
  for (const a of Object.values(state.agents)) if (rooms.has(a.room)) delete state.agents[a.id];
  renderHome();
}

async function deleteAgent(id) {
  await api(`/api/agents/${id}`, { method: 'DELETE' });
  delete state.agents[id];
  renderMembers();
  await pollEvents();
}

// ---- the chrome extension -------------------------------------------------
$('get-extension').addEventListener('click', () => {
  const open = $('extension-help').hidden;
  $('extension-help').hidden = !open;
  $('get-extension').setAttribute('aria-expanded', String(open));
  if (open) toggleForm(false);
});
$('copy-extensions-url').addEventListener('click', async (e) => {
  try {
    await navigator.clipboard.writeText('chrome://extensions');
    e.target.textContent = 'copied';
  } catch (_) { e.target.textContent = 'copy failed, type it in'; }
  setTimeout(() => { e.target.textContent = 'copy'; }, 1600);
});

// ---- new team ---------------------------------------------------------
function toggleForm(open) {
  if (open) { $('extension-help').hidden = true; $('get-extension').setAttribute('aria-expanded', 'false'); }
  $('team-form').hidden = !open;
  $('new-team').setAttribute('aria-expanded', String(open));
  $('form-error').hidden = true;
  if (open) $('team-form').elements.name.focus();
}

$('new-team').addEventListener('click', () => toggleForm($('team-form').hidden));
$('cancel-team').addEventListener('click', () => toggleForm(false));

$('team-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  const f = form.elements;
  const say = (msg) => { $('form-error').textContent = msg; $('form-error').hidden = false; };
  if (!f.name.value.trim()) { f.name.focus(); return say('give the team a name.'); }
  if (!/^[\w-]+\/[\w.-]+$/.test(f.repo.value.trim().replace(/^https:\/\/github\.com\//, '').replace(/\.git$/, ''))) {
    f.repo.focus(); return say('the repo should look like owner/name.');
  }
  const body = {
    name: f.name.value, repo: f.repo.value, purpose: f.purpose.value,
    rooms: f.rooms.value.split(',').map((r) => r.trim()).filter(Boolean),
    senses: [...form.querySelectorAll('input[name=senses]:checked')].map((c) => c.value),
  };
  if (!body.rooms.length) body.rooms = ['general'];
  const submit = form.querySelector('[type=submit]');
  submit.disabled = true;
  try {
    const made = await api('/api/teams', { method: 'POST', body: JSON.stringify(body) });
    state.teams.push(made.team);
    state.rooms.push(...made.rooms);
    for (const a of made.agents) state.agents[a.id] = a;
    form.reset();
    toggleForm(false);
    location.hash = `#/room/${made.rooms[0].id}`;
  } catch (err) {
    say(err.message);
  } finally { submit.disabled = false; }
});

function openHome() {
  state.room = null;
  delete document.body.dataset.group;
  $('app').hidden = true;
  $('home').hidden = false;
  document.title = 'renga';
  renderHome();
}

// ---- rooms ------------------------------------------------------------
function renderRooms() {
  const nav = $('rooms');
  nav.replaceChildren();
  for (const r of roomsOf(room(state.room).team)) {
    const b = el('a', 'room-btn');
    b.href = `#/room/${r.id}`;
    if (r.id === state.room) b.setAttribute('aria-current', 'page');
    b.append(el('span', 'hash', '#'), el('span', null, r.name));
    const n = state.unread[r.id] || 0;
    if (n && r.id !== state.room) b.appendChild(unreadBadge(n));
    nav.appendChild(b);
  }
}

function renderMembers() {
  const list = $('members');
  list.replaceChildren();
  for (const a of Object.values(state.agents)) {
    if (a.room !== state.room) continue;
    const li = el('li');
    const text = el('div');
    const name = el('div', 'm-name', a.name);
    if (isLead(a.id)) name.appendChild(el('span', 'lead-mark', 'lead'));
    text.append(name, el('div', 'm-role', a.role));
    const del = el('button', 'm-del', '×');
    del.type = 'button';
    del.setAttribute('aria-label', `remove ${a.name}`);
    del.addEventListener('click', () => confirmDelete(li, `remove ${a.name} from this room?`, () => deleteAgent(a.id)));
    li.append(avatar(a.id, true), text, del);
    list.appendChild(li);
  }
  const n = list.children.length;
  if (!n) list.appendChild(el('li', 'm-none', 'no agents yet'));
  $('crew-toggle').textContent = `agents · ${n}`;
}

// ---- the agents rail, and adding one ------------------------------------
// On wide screens the rail is always there; on narrow ones it's a drawer.
function toggleCrew(open) {
  $('crew').classList.toggle('open', open);
  $('crew-toggle').setAttribute('aria-expanded', String(open));
  if (open) $('crew-close').focus();
}
$('crew-toggle').addEventListener('click', () => toggleCrew(!$('crew').classList.contains('open')));
$('crew-close').addEventListener('click', () => { toggleCrew(false); $('crew-toggle').focus(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && $('crew').classList.contains('open')) toggleCrew(false); });

function toggleAgentForm(open) {
  $('agent-form').hidden = !open;
  $('add-agent').hidden = open;
  $('add-agent').setAttribute('aria-expanded', String(open));
  $('agent-error').hidden = true;
  if (open) $('agent-form').elements.name.focus();
}
$('add-agent').addEventListener('click', () => toggleAgentForm(true));
$('cancel-agent').addEventListener('click', () => { toggleAgentForm(false); $('add-agent').focus(); });

$('agent-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  const f = form.elements;
  const say = (msg) => { $('agent-error').textContent = msg; $('agent-error').hidden = false; };
  if (!f.name.value.trim()) { f.name.focus(); return say('give the agent a name.'); }
  if (!f.role.value.trim()) { f.role.focus(); return say('say what it does.'); }
  const body = {
    name: f.name.value, role: f.role.value,
    senses: [...form.querySelectorAll('input[name=senses]:checked')].map((c) => c.value),
  };
  const submit = form.querySelector('[type=submit]');
  submit.disabled = true;
  try {
    const a = await api(`/api/rooms/${state.room}/agents`, { method: 'POST', body: JSON.stringify(body) });
    state.agents[a.id] = a;
    form.reset();
    toggleAgentForm(false);
    renderMembers();
    await pollEvents();
  } catch (err) { say(err.message); } finally { submit.disabled = false; }
});

function openRoom(id) {
  toggleAgentForm(false);
  toggleCrew(false);
  const r = room(id);
  const t = team(r.team);
  state.room = id;
  state.unread[id] = 0;
  document.body.dataset.group = groupOf(id);
  $('home').hidden = true;
  $('app').hidden = false;
  document.title = `#${r.name} · ${t.name}`;
  $('team-name').textContent = t.name;
  $('team-repo').textContent = t.repo;
  $('team-repo').href = repoUrl(t.repo);
  $('room-name').textContent = `#${r.name}`;
  $('room-purpose').textContent = r.purpose;
  $('c-input').placeholder = `message #${r.name}`;
  renderRooms();
  renderMembers();
  renderLog();
}

function route() {
  $('library').hidden = true;
  const m = location.hash.match(/^#\/room\/([\w-]+)$/);
  if (m && room(m[1])) openRoom(m[1]);
  else if (location.hash === '#/library') openLibrary(); // library.js
  else openHome();
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
  const who = el('b', null, nameOf(event.from, event.data?.name));
  row.append(who, document.createTextNode(` ${event.text || event.kind.replace('_', ' ')}`));
  if (!event.data?.frame) return row;
  // What a screen reader saw: the screenshot, linking to the page it came from.
  const wrap = el('div', 'seen');
  const link = el('a', 'shot');
  link.href = event.data.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
  const img = el('img'); img.src = event.data.frame; img.alt = `screenshot of ${event.data.title || event.data.url}`;
  img.loading = 'lazy';
  link.appendChild(img);
  wrap.append(row, link);
  return wrap;
}

function messageRow(event, continues, prev) {
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
    const jump = el('a', 'jump', `open #${room(event.data.room).name} →`);
    jump.href = `#/room/${event.data.room}`;
    card.appendChild(jump);
    body.appendChild(card);
  } else if (event.kind === 'task' && event.data?.delegated_from) {
    const card = el('div', 'card');
    card.append(el('div', 'card-label', `brief from #${room(event.data.delegated_from)?.name}`),
                el('div', 'tx', event.text || ''));
    body.appendChild(card);
  } else {
    body.appendChild(el('div', 'tx', event.text || ''));
    if (event.kind === 'question') body.appendChild(questionCard(event));
    // Only where the trace changes: the lines under it belong to the same one.
    const trace = event.data?.trace_id;
    if (trace && trace !== prev?.data?.trace_id) body.appendChild(traceLink(trace));
  }

  row.append(avatar(event.from), body);
  return row;
}

// The trace a #logfire line is about: a link into logfire when the server
// knows the project, the bare id to search for when it doesn't.
function traceLink(id) {
  const short = `trace ${id.slice(0, 8)}`;
  if (!state.logfire) return el('div', 'trace', short);
  const link = el('a', 'trace', `${short} →`);
  link.href = `${state.logfire.replace(/\/$/, '')}?q=${encodeURIComponent(`trace_id='${id}'`)}`;
  link.target = '_blank'; link.rel = 'noopener noreferrer'; link.title = id;
  return link;
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
  return messageRow(event, continues, prev);
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
    if (!state.room) renderHome();
    else if (elsewhere) renderRooms();
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
    const [teams, rooms, agents] = await Promise.all(
      [api('/api/teams'), api('/api/rooms'), api('/api/agents')]);
    state.teams = teams;
    state.rooms = rooms;
    for (const a of agents) state.agents[a.id] = a;
    state.logfire = (await api('/api/logfire').catch(() => ({}))).url || null;
    await loadQuestions();
    await pollEvents();
    state.unread = {};
    route();
    window.addEventListener('hashchange', route);
    state.poll = setInterval(pollEvents, 1200);
  } catch (err) { showError(err.message); }
})();
