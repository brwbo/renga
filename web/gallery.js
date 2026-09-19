// a design room's library, #/room/<id>/library: every image its creative
// director signed off, final versions only, in a grid. it sits under the
// room in the sidebar. uses app.js's helpers (state, api, el, $, room,
// nameOf, openRoom) and work.js's fileTile, so it loads after them.
'use strict';

const shelf = { room: null, key: null };
const IMAGE_TYPES = new Set(['image/svg+xml', 'text/html']);

// The rooms a creative director leads are the ones that make images.
const hasLibrary = (r) => state.agents[r.lead]?.template === 'creative-director';

function openGallery(id) {
  state.gallery = true;
  openRoom(id);
  const r = room(id);
  $('app').classList.add('in-gallery');
  $('room-name').textContent = `#${r.name} / library`;
  $('room-purpose').textContent = `every image ${nameOf(r.lead)} signed off. final versions only.`;
  document.title = `library · #${r.name}`;
  shelf.room = null;
  $('gallery').replaceChildren();
  refreshGallery();
}

// The room's last sign-off, so the grid refetches only when there's a new one.
function lastSignOffIn(roomId) {
  const events = state.events[roomId] || [];
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].kind === 'announce_done' && events[i].data?.deliverables) return events[i].id;
  }
  return 0;
}

async function refreshGallery() {
  const id = state.room;
  const key = lastSignOffIn(id);
  if (shelf.room === id && shelf.key === key) return;
  shelf.room = id; shelf.key = key;
  try {
    renderGallery(await api(`/api/rooms/${id}/library`));
  } catch (err) {
    $('gallery').replaceChildren(el('p', 'form-err', err.message));
  }
}

function renderGallery(sets) {
  const grid = el('div', 'gallery-grid');
  for (const s of sets) {
    const when = new Date(s.ts).toLocaleDateString([], { day: 'numeric', month: 'short' });
    for (const p of s.pieces) {
      for (const f of p.files.filter((x) => x.url && IMAGE_TYPES.has(x.type))) {
        const tile = fileTile(f); // work.js
        tile.title = s.brief ? `${f.name}\n\n${s.brief}` : f.name;
        tile.querySelector('.file-name').textContent = `${p.by ? nameOf(p.by) : p.role} · ${when}`;
        grid.appendChild(tile);
      }
    }
  }
  $('gallery').replaceChildren(grid.children.length ? grid : el('p', 'empty', 'nothing signed off yet.'));
}
