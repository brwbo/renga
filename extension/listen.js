// the "hear the call" bar: lets the team's listener hear a meet call without
// captions. chrome only lets an extension record a tab from your click, so
// this is a button: click it with the call in front, and the call's audio
// goes to renga to be transcribed as the listener (background.js,
// offscreen.js). uses panel.js's helpers (state, el, $, senser, showError,
// hasChrome), so it loads after it.
'use strict';

const CALL = /^https:\/\/meet\.google\.com\/.+/;

async function renderEars() {
  const slot = $('ears-slot');
  const who = hasChrome && senser('captions');
  if (!who) { slot.replaceChildren(); return; }
  const { ears } = await chrome.runtime.sendMessage({ type: 'get-ears' }).catch(() => ({ ears: null }));
  // Only shown while the listener is hearing a call, as the way to stop it.
  if (!ears) { slot.replaceChildren(); return; }

  const bar = el('button', 'rail');
  bar.type = 'button';
  bar.append(el('span', 'rec'), el('span', 'note', `${who.name} is hearing the call. click to stop`));
  bar.setAttribute('aria-pressed', 'true');
  bar.addEventListener('click', stopEars);
  slot.replaceChildren(bar);
}

async function startEars(who) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !CALL.test(tab.url || '')) throw new Error('open the meet call in this window, then click again.');
    const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });
    const r = await chrome.runtime.sendMessage({ type: 'ears-start', streamId, tabId: tab.id, agentId: who.id });
    if (!r?.ok) throw new Error(r?.reason || "couldn't start hearing the call.");
    showError('');
  } catch (err) { showError(err.message); }
  renderEars();
}

async function stopEars() {
  await chrome.runtime.sendMessage({ type: 'ears-stop' }).catch(() => {});
  renderEars();
}

if (hasChrome) {
  setInterval(renderEars, 3000); // a team switch, a call opening or closing
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'ears-ended') { if (msg.reason) showError(`stopped hearing the call: ${msg.reason}`); renderEars(); }
  });
  renderEars();
}
