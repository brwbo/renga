// the team's context doc, and the work agents post. uses app.js's helpers
// (state, api, el, $, showError), so it loads after it.
'use strict';

// ---- context: one markdown doc per team, read by every agent in it --------
const ctx = { team: null, text: '' };

async function loadContext(t) {
  if (ctx.team === t.id) return;
  ctx.team = t.id;
  ctx.text = '';
  $('context-team').textContent = t.name;
  showContextState();
  try {
    const got = await api(`/api/teams/${t.id}/context`);
    if (ctx.team === t.id) { ctx.text = got.text; showContextState(); }
  } catch (err) { showError(err.message); }
}

function showContextState() {
  const lines = ctx.text ? ctx.text.split('\n').filter((l) => l.trim()).length : 0;
  $('context-state').textContent = lines ? `${lines} line${lines === 1 ? '' : 's'}` : 'add';
  $('context-open').classList.toggle('empty', !lines);
}

function contextError(msg) {
  $('context-error').textContent = msg || '';
  $('context-error').hidden = !msg;
}

$('context-open').addEventListener('click', () => {
  $('context-text').value = ctx.text;
  contextError('');
  $('context-dialog').showModal();
  $('context-text').focus();
});
$('context-cancel').addEventListener('click', () => $('context-dialog').close());

$('context-file').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  if (file.size > 50000) return contextError(`${file.name} is over 50kb. trim it down first.`);
  const text = await file.text();
  const box = $('context-text');
  box.value = box.value.trim() ? `${box.value.trimEnd()}\n\n${text}` : text;
  contextError('');
});

$('context-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const save = e.target.querySelector('[type=submit]');
  save.disabled = true;
  try {
    const got = await api(`/api/teams/${ctx.team}/context`,
      { method: 'PUT', body: JSON.stringify({ text: $('context-text').value }) });
    ctx.text = got.text;
    showContextState();
    $('context-dialog').close();
  } catch (err) { contextError(err.message); } finally { save.disabled = false; }
});

// ---- work: what an agent made, shown in the chat --------------------------
// svg shows as an image, html as a live preview (sandboxed: no scripts),
// anything else as a file to open. the files are served sandboxed too.
function workCard(row, event) {
  const wrap = el('div', 'work');
  wrap.appendChild(row);
  const files = event.data.files || [];
  if (files.length) {
    const grid = el('div', 'work-files');
    for (const f of files) grid.appendChild(fileTile(f));
    wrap.appendChild(grid);
  }
  if (event.data.deliverable) {
    const more = el('details', 'work-text');
    more.append(el('summary', null, 'the work'), el('div', 'tx', event.data.deliverable));
    wrap.appendChild(more);
  }
  return wrap;
}

function fileTile(f) {
  const tile = el('a', 'file');
  tile.href = f.url; tile.target = '_blank'; tile.rel = 'noopener noreferrer';
  tile.title = `open ${f.name}`;
  if (f.type === 'image/svg+xml') {
    const img = el('img');
    img.src = f.url; img.alt = f.name; img.loading = 'lazy';
    tile.appendChild(el('div', 'file-view')).appendChild(img);
  } else if (f.type === 'text/html') {
    const frame = el('iframe');
    frame.src = f.url; frame.title = f.name; frame.loading = 'lazy';
    frame.setAttribute('sandbox', '');
    frame.tabIndex = -1;
    tile.appendChild(el('div', 'file-view page')).appendChild(frame);
  } else {
    tile.appendChild(el('div', 'file-view doc', `.${f.name.split('.').pop()}`));
  }
  tile.appendChild(el('div', 'file-name', f.name));
  return tile;
}
