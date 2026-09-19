// Reads google meet's own live captions and hands new text to the worker,
// which posts it into the meeting room as the team's captions agent.
//
// This is the fast first version from the plan: meet already does the speech
// to text and knows who is speaking. It depends on meet's page, which google
// changes without notice, so it looks for the captions region by its
// accessible name rather than by class names, and reports honestly when it
// can't find it. Real audio capture replaces this later.
'use strict';

(() => {
  const STABLE_MS = 1500;   // the captions count as said once they stop changing
  const POLL_MS = 500;
  const BEAT_MS = 10000;    // re-report the status, so a restarted worker knows it

  const findRegion = () =>
    document.querySelector('[role="region"][aria-label*="aption" i]') ||
    document.querySelector('[aria-label="Captions"]');

  let status = null, reported = 0;
  function report(next) {
    if (next === status && Date.now() - reported < BEAT_MS) return;
    status = next;
    reported = Date.now();
    try { chrome.runtime.sendMessage({ type: 'captions-status', status }); } catch (_) { /* reloaded */ }
  }

  // What's new on screen since the last send. Meet's captions are a window
  // that scrolls: old lines leave the top, new ones arrive at the bottom, and
  // the line being spoken keeps growing. So line up the end of what was sent
  // with the start of what's shown, and send only what comes after it. A
  // speaker's name that comes back later is new again, not a repeat.
  function fresh(prev, cur) {
    for (let s = 0; s < prev.length; s++) {
      const tail = prev.slice(s);
      if (tail.length > cur.length) continue;
      if (tail.slice(0, -1).some((line, j) => line !== cur[j])) continue;
      const last = tail[tail.length - 1], now = cur[tail.length - 1];
      if (now === last) return cur.slice(tail.length);
      if (now.startsWith(last)) {
        const more = now.slice(last.length).trim();
        return [...(more ? [`… ${more}`] : []), ...cur.slice(tail.length)];
      }
      return cur.slice(tail.length - 1); // meet rewrote the last line: send it again
    }
    return cur;
  }

  let sent = [], lastText = '', lastChange = 0;

  function tick() {
    const region = findRegion();
    if (!region) { report('missing'); return; }
    report('on');

    const text = region.innerText.trim();
    const now = Date.now();
    if (text !== lastText) { lastText = text; lastChange = now; return; }
    if (!text || now - lastChange < STABLE_MS) return;

    const cur = text.split('\n').map((l) => l.trim()).filter(Boolean);
    const lines = fresh(sent, cur);
    sent = cur;
    if (!lines.length) return;
    try {
      chrome.runtime.sendMessage({ type: 'caption', text: lines.join('\n') });
    } catch (_) { /* extension reloaded; this tab's script is orphaned */ }
  }

  setInterval(tick, POLL_MS);
})();
