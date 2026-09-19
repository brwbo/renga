// Reads google meet's own live captions and hands finished lines to the
// worker, which posts them into the meeting room as the transcript agent.
//
// This is the fast first version from the plan: meet already does the speech
// to text and knows who is speaking. It depends on meet's page, which google
// changes without notice, so it looks for the captions region by its
// accessible name rather than by class names, and reports honestly when it
// can't find it. Real audio capture replaces this later.
'use strict';

(() => {
  const STABLE_MS = 1500;   // a caption line counts as finished once it stops changing
  const POLL_MS = 500;

  const findRegion = () =>
    document.querySelector('[role="region"][aria-label*="aption" i]') ||
    document.querySelector('[aria-label="Captions"]');

  let status = null;
  function report(next) {
    if (next === status) return;
    status = next;
    try { chrome.runtime.sendMessage({ type: 'captions-status', status }); } catch (_) { /* reloaded */ }
  }

  // Lines already sent, so a caption that stays on screen isn't sent twice.
  // Bounded, because a long call would otherwise grow it forever.
  const sent = [];
  const alreadySent = (line) => sent.includes(line);
  const remember = (line) => { sent.push(line); if (sent.length > 200) sent.shift(); };

  let lastText = '', lastChange = 0;

  function tick() {
    const region = findRegion();
    if (!region) { report('missing'); return; }
    report('on');

    const text = region.innerText.trim();
    const now = Date.now();
    if (text !== lastText) { lastText = text; lastChange = now; return; }
    if (!text || now - lastChange < STABLE_MS) return;

    const fresh = text.split('\n').map((l) => l.trim()).filter((l) => l && !alreadySent(l));
    if (!fresh.length) return;
    fresh.forEach(remember);
    try {
      chrome.runtime.sendMessage({ type: 'caption', text: fresh.join('\n') });
    } catch (_) { /* extension reloaded; this tab's script is orphaned */ }
  }

  setInterval(tick, POLL_MS);
})();
