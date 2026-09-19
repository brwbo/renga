// "+ new room" under a team's rooms: a name and what it's for. the room
// starts empty; add agents to it from the agents rail, as in any room. uses
// app.js's helpers (state, api, $, room, renderRooms), so it loads after it.
'use strict';

function toggleRoomForm(open) {
  $('room-form').hidden = !open;
  $('add-room').hidden = open;
  $('add-room').setAttribute('aria-expanded', String(open));
  $('room-error').hidden = true;
  if (open) $('room-form').elements.name.focus();
}
$('add-room').addEventListener('click', () => toggleRoomForm(true));
$('cancel-room').addEventListener('click', () => { toggleRoomForm(false); $('add-room').focus(); });
window.addEventListener('hashchange', () => toggleRoomForm(false));

$('room-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  const f = form.elements;
  const say = (msg) => { $('room-error').textContent = msg; $('room-error').hidden = false; };
  if (!f.name.value.trim()) { f.name.focus(); return say('give the room a name.'); }
  const submit = form.querySelector('[type=submit]');
  submit.disabled = true;
  try {
    const team = room(state.room).team;
    const made = await api(`/api/teams/${team}/rooms`, {
      method: 'POST', body: JSON.stringify({ name: f.name.value, purpose: f.purpose.value }),
    });
    state.rooms.push(made);
    form.reset();
    toggleRoomForm(false);
    location.hash = `#/room/${made.id}`;
  } catch (err) { say(err.message); } finally { submit.disabled = false; }
});
