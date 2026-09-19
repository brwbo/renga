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
  loadContext(t); // work.js
  renderTeam();
  renderTeamContext();
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


// ---- the team's context: the doc every agent in the team reads -----------
function renderTeamContext() {
  if (!state.team || ctx.team !== state.team) return;
  const text = ctx.text.trim();
  $('tv-context-text').hidden = !text;
  $('tv-context-text').textContent = text;
  $('tv-context-empty').hidden = !!text;
  $('tv-context-edit').textContent = text ? 'edit' : 'add context';
}
$('tv-context-edit').addEventListener('click', openContext); // work.js
