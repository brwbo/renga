// Notices when someone in the meet call starts presenting, and while they
// are, nudges the worker every TICK_MS to look at the call for a new slide
// (background.js does the looking: only it can take a screenshot). Meet
// changes its markup without notice, so this goes by the words meet shows
// ("is presenting", "stop presenting", a "(presentation)" tile), never by
// class names.
(() => {
  const TICK_MS = 1500;
  const SAYS = /\b(is|are) presenting\b|\byou'?re presenting\b|\bstop presenting\b|\(presentation\)|\bpresentation from\b/i;
  const NOT = /\bpresent now\b|\bstart presenting\b/i;

  function presenting() {
    for (const node of document.querySelectorAll('[aria-label]')) {
      const label = node.getAttribute('aria-label') || '';
      if (SAYS.test(label) && !NOT.test(label)) return true;
    }
    return SAYS.test((document.body?.innerText || '').slice(0, 20000));
  }

  const tell = (msg) => { try { chrome.runtime.sendMessage(msg); } catch (_) { /* extension reloaded */ } };

  let on = false;
  setInterval(() => {
    const now = presenting();
    if (now !== on) { on = now; tell({ type: 'presenting', on }); }
    if (on) tell({ type: 'slide-tick' });
  }, TICK_MS);
})();
