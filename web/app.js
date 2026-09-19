// the room: a group chat where the agents talk in plain english and you sit
// in with them. Plain script, no build step. The chat view and the sprite
// drawing are carried over from agentville's web/app.js.
'use strict';

const $ = (id) => document.getElementById(id);
const S = window.Sprites;
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

// ---- sprites ----------------------------------------------------------
const BUST = { x0: 12, y0: 5, w: 20, h: 31 };   // head, shoulders and chest:
// the chest is in the crop because that is where the outfit says what the job is
const ADMIN_SPRITE = { skin: 1, hair: 'brown', style: 'parted', accent: 'red', eyes: 'green',
                       tie: 'tie', face: 'none', extra: 'none', outfit: 'turtle', hat: 'none',
                       work: 'typing' };

// Transparent so a character sits on the panel, not in a lit box cut out of it.
function drawBust(canvas, spec, scale) {
  const grid = S.build(spec, 'idle', 0), pal = S.palette(spec);
  canvas.width = BUST.w * scale; canvas.height = BUST.h * scale;
  const ctx = canvas.getContext('2d');
  for (let y = 0; y < BUST.h; y++) for (let x = 0; x < BUST.w; x++) {
    const c = grid[BUST.y0 + y] && grid[BUST.y0 + y][BUST.x0 + x];
    if (!c || c === '.') continue;
    ctx.fillStyle = pal[c] || '#f0f';
    ctx.fillRect(x * scale, y * scale, scale, scale);
  }
}

const bust = (spec, scale = 2) => {
  const c = document.createElement('canvas');
  drawBust(c, spec, scale);
  return c;
};

// ---- api --------------------------------------------------------------
function setConn(on) {
  $('s-conn').textContent = on ? 'connected' : 'offline';
  $('s-dot').classList.toggle('off', !on);
}

async function api(path, options) {
  let res;
  try {
    res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  } catch (err) {
    setConn(false);
    throw err;
  }
  setConn(true);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) { /* not json */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? null : res.json();
}

function showError(message) {
  $('error').textContent = message;
  $('error').classList.toggle('hidden', !message);
}

const CHANNEL = 'main';
const state = { agents: {}, since: 0, poll: null, questions: {}, answered: new Set(), stage: null };

// ---- roster -----------------------------------------------------------
async function loadRoster() {
  const agents = await api('/api/agents');
  state.agents = {};
  const strip = $('roster');
  strip.innerHTML = '';
  for (const a of agents) {
    state.agents[a.id] = a;
    const box = el('div', a.lead ? 'member pm' : 'member');
    box.title = a.role;
    box.append(bust(a.sprite, 2), el('div', null, a.name));
    strip.appendChild(box);
  }
}

// ---- messages ---------------------------------------------------------
function spriteFor(from) {
  if (from === 'admin') return ADMIN_SPRITE;
  const card = state.agents[from];
  return card ? card.sprite : null;
}

function answerBox(question) {
  const wrap = el('div', 'answer');
  // Choice questions are buttons, not a dropdown.
  if (question.options && question.options.length) {
    for (const opt of question.options) {
      const b = el('button', null, opt); b.type = 'button';
      b.addEventListener('click', () => submitAnswer(question, opt, wrap));
      wrap.appendChild(b);
    }
    return wrap;
  }
  const field = el('input');
  field.type = 'text';
  field.placeholder = 'your answer';
  field.autocomplete = 'off';
  const send = el('button', null, 'answer');
  send.type = 'button';
  const go = () => submitAnswer(question, field.value.trim(), wrap);
  send.addEventListener('click', go);
  field.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); go(); } });
  wrap.append(field, send);
  return wrap;
}

async function submitAnswer(question, value, wrap) {
  if (!value) return;
  try {
    await api(`/api/questions/${question.id}/answer`,
              { method: 'POST', body: JSON.stringify({ value }) });
    state.answered.add(question.id);
    wrap.replaceWith(el('div', 'answered', '✓ answered'));
    await pollEvents();
  } catch (err) { showError(err.message); }
}

// The newest spoken line stands on stage in the console; when the next one
// arrives it drops back into the transcript, in the slot it was spoken in.
// Portraits are redrawn rather than CSS-scaled: these are pixels, and a
// fractional scale would smear them.
const STAGE_SCALE = 3, LOG_SCALE = 2;
const SPOKEN = new Set(['chat', 'question', 'answer', 'handoff']);
const STATUS = { announce_start: 'msg sys work', announce_done: 'msg sys work', error: 'msg sys fail' };

function demoteStage() {
  const stage = state.stage;
  if (!stage) return;
  state.stage = null;
  if (stage.portrait) drawBust(stage.portrait, stage.sprite, LOG_SCALE);
  stage.anchor.replaceWith(stage.row);
}

function nameOf(id) {
  return id === 'admin' ? 'you' : (state.agents[id]?.name || id);
}

function addMessage(event) {
  const log = $('log');
  const sprite = spriteFor(event.from);
  const isLead = state.agents[event.from]?.lead;

  // Status lines (started, finished, failed) are small and go straight into
  // the transcript; they never take the stage from someone speaking.
  if (!SPOKEN.has(event.kind) || !sprite) {
    const row = el('div', STATUS[event.kind] || 'msg sys');
    row.append(el('div', 'tx', `${nameOf(event.from)}: ${event.text || event.kind}`));
    if (state.stage) state.stage.anchor.before(row); else log.appendChild(row);
    log.scrollTop = log.scrollHeight;
    return;
  }

  const row = el('div', `msg${isLead ? ' pm' : ''}`);
  const col = el('div', 'bd');
  let who = nameOf(event.from);
  if (event.to) who += ` → ${nameOf(event.to)}`;
  col.append(el('div', 'who', who), el('div', 'tx', event.text || ''));
  const qid = event.data && event.data.question_id;
  if (event.kind === 'question' && qid && !state.answered.has(qid) && state.questions[qid]) {
    col.appendChild(answerBox(state.questions[qid]));
  }
  const portrait = bust(sprite, STAGE_SCALE);
  row.append(portrait, col);

  // An anchor holds this message's place in the transcript while it is on
  // stage, so a status line landing behind it can't jump the order.
  const anchor = el('div', 'anchor');
  log.appendChild(anchor);
  demoteStage();
  state.stage = { row, anchor, portrait, sprite };
  $('spotlight').replaceChildren(row);
  log.scrollTop = log.scrollHeight;
}

async function loadQuestions() {
  const open = await api(`/api/questions?channel=${CHANNEL}`);
  state.questions = {};
  for (const q of open) state.questions[q.id] = q;
}

async function pollEvents() {
  try {
    const events = await api(`/api/events?channel=${CHANNEL}&since=${state.since}`);
    if (events.some((e) => e.data && e.data.question_id && !state.questions[e.data.question_id])) {
      await loadQuestions();
    }
    for (const event of events) {
      state.since = Math.max(state.since, event.id);
      addMessage(event);
    }
  } catch (_) { /* setConn already reflected it */ }
}

function startPolling() { if (state.poll) clearInterval(state.poll); state.poll = setInterval(pollEvents, 1200); }

$('composer').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('c-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  try {
    await api('/api/chat', { method: 'POST', body: JSON.stringify({ text, channel: CHANNEL }) });
    showError('');
    await pollEvents();
  } catch (err) { showError(err.message); input.value = text; }
});

// ---- boot -------------------------------------------------------------
(async () => {
  try {
    await loadRoster();
    await loadQuestions();
    await pollEvents();
    startPolling();
  } catch (err) { showError(err.message); }
})();
