// a whole team at once, #/team/<id>: every room, who's in it, who leads it
// and what was last said. uses app.js's helpers (state, team, roomsOf,
// avatar, isLead, groupOf, lastLine, nameOf, el, $), so it loads after it.
'use strict';

const SENSES = { screen: 'reads the tab you\'re on', captions: 'hears meet calls' };

function openTeam(id) {
  const t = team(id);
  state.room = null;
  state.team = id;
  delete document.body.dataset.group;
  $('app').hidden = true;
  $('home').hidden = true;
  $('team-view').hidden = false;
  document.title = `${t.name} · renga`;
  if (outputs.team !== id) { outputs.sets = []; $('tv-outputs').replaceChildren(); }
  renderTeam();
}

function renderTeam() {
  const t = team(state.team);
  if (!t) return;
  $('tv-name').textContent = t.name;
  $('tv-purpose').textContent = t.purpose;
  $('tv-repo').textContent = t.repo;
  $('tv-repo').href = repoUrl(t.repo);

  const rooms = roomsOf(t.id);
  const agents = Object.values(state.agents).filter((a) => rooms.some((r) => r.id === a.room));
  $('tv-count').textContent = `${rooms.length} room${rooms.length === 1 ? '' : 's'} · `
    + `${agents.length} agent${agents.length === 1 ? '' : 's'}`;

  const grid = $('tv-rooms');
  grid.replaceChildren();
  for (const r of rooms) grid.appendChild(roomCard(r, agents.filter((a) => a.room === r.id)));
  loadOutputs(t.id);
}

function roomCard(r, members) {
  const card = el('section', 'team-card tv-room');
  card.dataset.group = groupOf(r.id);
  card.setAttribute('aria-labelledby', `tv-${r.id}`);

  const head = el('div', 'team-card-head');
  const h = el('h2'); h.id = `tv-${r.id}`;
  h.append(el('span', 'hash', '#'), r.name);
  head.appendChild(h);
  if (state.unread[r.id]) head.appendChild(unreadBadge(state.unread[r.id]));
  card.append(head, el('p', 'team-purpose', r.purpose || ' '));

  const list = el('ul', 'members tv-members');
  // the lead first, then everyone else in the order they joined
  for (const a of [...members].sort((x, y) => isLead(y.id) - isLead(x.id))) {
    const li = el('li');
    const text = el('div');
    const name = el('div', 'm-name', a.name);
    if (r.lead === a.id) name.appendChild(el('span', 'lead-mark', 'lead'));
    text.append(name, el('div', 'm-role', a.role));
    for (const s of a.senses || []) if (SENSES[s]) text.appendChild(el('div', 'tv-sense', SENSES[s]));
    li.append(avatar(a.id, true), text);
    list.appendChild(li);
  }
  if (!members.length) list.appendChild(el('li', 'm-none', 'no agents yet'));
  card.appendChild(list);

  const last = lastLine(r.id);
  if (last) card.appendChild(el('p', 'tv-last', `${nameOf(last.from)}: ${last.text}`));

  const open = el('a', 'jump tv-open', `open #${r.name} →`);
  open.href = `#/room/${r.id}`;
  card.appendChild(open);
  return card;
}

// ---- approved work: what each room's lead signed off, newest first ---------
const outputs = { team: null, key: null, sets: [] };

// The last sign-off in the team's rooms, so the library refetches only when
// there's a new one.
function lastSignOff(teamId) {
  let last = 0;
  for (const r of roomsOf(teamId)) {
    for (const e of state.events[r.id] || []) {
      if (e.kind === 'announce_done' && e.data?.deliverables && e.id > last) last = e.id;
    }
  }
  return last;
}

async function loadOutputs(teamId) {
  const key = lastSignOff(teamId);
  if (outputs.team === teamId && outputs.key === key) return;
  outputs.team = teamId; outputs.key = key;
  try {
    outputs.sets = await api(`/api/teams/${teamId}/outputs`);
  } catch (err) {
    outputs.sets = [];
    $('tv-outputs').replaceChildren(el('p', 'form-err', err.message));
    return;
  }
  if (state.team === teamId) renderOutputs();
}

function renderOutputs() {
  const host = $('tv-outputs');
  host.replaceChildren();
  if (!outputs.sets.length) {
    host.appendChild(el('p', 'm-none', 'nothing signed off yet.'));
    return;
  }
  for (const s of outputs.sets) host.appendChild(outputSet(s));
}

function outputSet(s) {
  const box = el('article', 'tv-set');
  box.dataset.group = groupOf(s.room);
  const head = el('div', 'tv-set-head');
  const where = el('a', 'tv-set-room', `#${room(s.room)?.name || s.room}`);
  where.href = `#/room/${s.room}`;
  const when = new Date(s.ts).toLocaleDateString([], { day: 'numeric', month: 'short' });
  head.append(where, el('span', 'tv-set-meta', `signed off by ${nameOf(s.lead)} · ${when} · ${clock(s.ts)}`));
  box.appendChild(head);
  if (s.brief) box.appendChild(el('p', 'tv-set-brief', s.brief));

  const grid = el('div', 'work-files tv-set-files');
  const texts = [];
  for (const p of s.pieces) {
    const files = p.files.filter((f) => f.url);
    for (const f of files) {
      const tile = fileTile(f); // work.js
      tile.querySelector('.file-name').textContent = `${f.name} · ${p.by ? nameOf(p.by) : p.role}`;
      grid.appendChild(tile);
    }
    if (!files.length) texts.push(p);
  }
  if (grid.children.length) box.appendChild(grid);
  for (const p of texts) {
    const more = el('details', 'work-text');
    more.append(el('summary', null, `${p.by ? nameOf(p.by) : p.role.replace(/-/g, ' ')}: the work`),
                el('div', 'tx', p.deliverable));
    box.appendChild(more);
  }
  return box;
}
