// who is thinking in the room you're in: moving dots above the composer.
// the same file runs in the web app and the extension's side panel, on their
// own helpers (state, api, el, $, avatar, nameOf), so it loads after them.
'use strict';

async function pollThinking() {
  let now = {};
  try { now = await api('/api/thinking'); } catch (_) { /* the event poll shows the error */ }
  const box = $('thinking');
  const who = (state.room && now[state.room]) || [];
  box.hidden = !who.length;
  if (!who.length) { box.replaceChildren(); return; }
  const names = who.map((id) => nameOf(id));
  const text = names.length > 2 ? `${names.length} agents are thinking`
    : `${names.join(' and ')} ${names.length === 1 ? 'is' : 'are'} thinking`;
  const faces = el('span', 'thinking-faces');
  for (const id of who.slice(0, 3)) faces.appendChild(avatar(id, true));
  const dots = el('span', 'dots');
  dots.setAttribute('aria-hidden', 'true');
  dots.append(el('i'), el('i'), el('i'));
  const label = el('span', 'thinking-text', text);
  // only re-announce when who is thinking changes, not every poll
  if (box.dataset.who !== who.join()) box.replaceChildren(faces, label, dots);
  box.dataset.who = who.join();
}

setInterval(pollThinking, 1000);
