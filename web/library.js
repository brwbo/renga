// the agent library, #/library. premade workflows set up whole rooms of
// agents in a team; premade agents join any room. uses app.js's helpers
// (state, api, el, $, showError), so it loads after it.
'use strict';

const lib = { data: null };
const GROUPS = [
  ['meeting', 'hear the meeting and hand out what needs doing'],
  ['design', 'visuals, layout, product and brand'],
  ['marketing', 'campaigns, copy, social and content'],
];

async function openLibrary() {
  state.room = null;
  $('app').hidden = true;
  $('home').hidden = true;
  $('library').hidden = false;
  document.title = 'agent library · renga';
  try {
    lib.data = lib.data || await api('/api/library');
    showError('');
    renderWorkflows();
    renderLibraryAgents();
  } catch (err) { showError(err.message); }
}

const libRole = (id) => lib.data.agents.find((a) => a.id === id);

function libAvatar(roleId, lead) {
  const node = el('span', 'av sm' + (lead ? ' lead' : ''), libRole(roleId)?.initials || roleId.slice(0, 2));
  node.title = roleId.replace(/-/g, ' ') + (lead ? ', leads the room' : '');
  return node;
}

function picker(label, options) {
  const wrap = el('label', 'lib-pick');
  wrap.append(el('span', 'sr', label));
  const select = el('select');
  for (const [group, items] of options) {
    const parent = group ? el('optgroup') : select;
    if (group) { parent.label = group; select.append(parent); }
    for (const [value, text] of items) {
      const o = el('option', null, text);
      o.value = value;
      parent.append(o);
    }
  }
  wrap.append(select);
  return { wrap, select };
}

// A row with a picker, a button and a line that says how it went.
function action(label, options, button, onGo) {
  const row = el('div', 'lib-act');
  const { wrap, select } = picker(label, options);
  const go = el('button', 'btn', button);
  go.type = 'button';
  const note = el('p', 'lib-note');
  note.setAttribute('role', 'status');
  go.addEventListener('click', async () => {
    go.disabled = true;
    note.classList.remove('bad');
    try {
      note.replaceChildren(...await onGo(select.value));
    } catch (err) {
      note.textContent = err.message;
      note.classList.add('bad');
    } finally { go.disabled = false; }
  });
  row.append(wrap, go);
  return [row, note];
}

function roomLink(r) {
  const a = el('a', null, `#${r.name}`);
  a.href = `#/room/${r.id}`;
  return a;
}

// ---- workflows ----------------------------------------------------------
function renderWorkflows() {
  const grid = $('workflows');
  grid.replaceChildren();
  const teams = [[null, state.teams.map((t) => [t.id, t.name])]];
  for (const w of lib.data.workflows) {
    const card = el('section', 'team-card lib-card' + (w.how.length ? ' lib-feature' : ''));
    card.append(el('h3', null, w.name), el('p', 'team-purpose', w.does));
    if (w.how.length) {
      const steps = el('ol', 'lib-how');
      for (const s of w.how) steps.append(el('li', null, s));
      card.append(steps);
    }
    const rooms = el('div', 'lib-rooms');
    for (const r of w.rooms) {
      const row = el('div', 'lib-room');
      row.append(el('span', 'tr-name', `#${r.name}`));
      const faces = el('span', 'lib-faces');
      for (const m of r.members) faces.append(libAvatar(m, m === r.lead));
      row.append(faces);
      rooms.append(row);
    }
    card.append(rooms);
    card.append(...action('set it up in', teams, 'set up', async (teamId) => {
      const made = await api(`/api/workflows/${w.id}/start`, {
        method: 'POST', body: JSON.stringify({ team: teamId }),
      });
      state.rooms.push(...made.rooms);
      for (const a of made.agents) state.agents[a.id] = a;
      renderLibraryAgents();
      const links = made.rooms.flatMap((r, i) => (i ? [', ', roomLink(r)] : [roomLink(r)]));
      return [`set up in ${team(teamId).name}: `, ...links];
    }));
    grid.append(card);
  }
}

// ---- agents -------------------------------------------------------------
function roomOptions() {
  return state.teams.map((t) => [t.name, roomsOf(t.id).map((r) => [r.id, `#${r.name}`])])
    .filter(([, rooms]) => rooms.length);
}

function renderLibraryAgents() {
  const host = $('library-agents');
  host.replaceChildren();
  const rooms = roomOptions();
  for (const [group, about] of GROUPS) {
    const section = el('section', 'lib-group');
    section.append(el('h3', 'lib-sub', group), el('p', 'purpose', about));
    const grid = el('div', 'lib-grid');
    for (const a of lib.data.agents.filter((x) => x.group === group)) {
      const card = el('article', 'team-card lib-card lib-agent');
      const head = el('div', 'lib-agent-head');
      head.append(libAvatar(a.id, false), el('h4', null, a.name));
      card.append(head, el('p', 'team-purpose', a.does));
      if (a.senses.includes('captions')) {
        card.append(el('p', 'lib-sense', 'hears meet calls through the chrome extension'));
      }
      card.append(...action(`add the ${a.name} to`, rooms, 'add', async (roomId) => {
        const made = await api(`/api/rooms/${roomId}/agents`, {
          method: 'POST', body: JSON.stringify({ template: a.id }),
        });
        state.agents[made.id] = made;
        return [`${made.name} joined `, roomLink(room(roomId))];
      }));
      grid.append(card);
    }
    section.append(grid);
    host.append(section);
  }
}
