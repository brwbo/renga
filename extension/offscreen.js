// the listener's ears when the call has no captions. an offscreen page
// (manifest v3 records audio only in one): it records the meet tab the
// panel picked, keeps playing it so you still hear the call, and posts what
// was said as a 16 kHz mono wav to renga, which has gemini transcribe it as
// the listener. a chunk ends where the speaker pauses (or at MAX_S in a long
// turn), so a sentence goes as soon as it's said rather than waiting out a
// fixed stretch. chunks with nobody talking are never sent.
'use strict';

const SERVER = 'http://localhost:8020';
const RATE = 16000;    // plenty for speech, and a third of the size of 48 kHz
const QUIET = 0.008;   // rms below this: nobody's speaking
const PAUSE_S = 0.5;   // this much quiet after speech ends a chunk...
const SPEECH_S = 0.6;  // ...once there's been at least this much speech in it
const MAX_S = 6;       // a long turn is cut here anyway
const LEAD_S = 0.3;    // quiet kept before speech starts, so its first word isn't clipped

let ears = null;

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.target !== 'offscreen') return;
  if (msg.type === 'ears-start') start(msg).catch((err) => ended(err.message));
  if (msg.type === 'ears-stop') stop();
});

async function start({ streamId, agentId }) {
  stop();
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { mandatory: { chromeMediaSource: 'tab', chromeMediaSourceId: streamId } },
    video: false,
  });
  const ctx = new AudioContext();
  const source = ctx.createMediaStreamSource(stream);
  source.connect(ctx.destination); // capturing a tab mutes it: play it back so you still hear the call
  const tap = ctx.createScriptProcessor(2048, 1, 1);  // ~43 ms blocks at 48 kHz
  let buf = [], len = 0, speech = 0, quiet = 0;  // samples: the chunk, speech in it, quiet at its end
  const rate = ctx.sampleRate;
  const flush = () => {
    const chunk = buf;
    buf = []; len = speech = quiet = 0;
    if (chunk.length) send(chunk, rate, agentId);
  };
  tap.onaudioprocess = (e) => {
    const block = new Float32Array(e.inputBuffer.getChannelData(0));
    e.outputBuffer.getChannelData(0).fill(0); // the tap itself stays silent
    buf.push(block);
    len += block.length;
    if (rms(block) >= QUIET) { speech += block.length; quiet = 0; } else quiet += block.length;
    if (!speech) {  // nobody's spoken yet: keep only a short lead-in
      while (buf.length > 1 && len - buf[0].length >= LEAD_S * rate) len -= buf.shift().length;
      return;
    }
    const paused = speech >= SPEECH_S * rate && quiet >= PAUSE_S * rate;
    if (paused || len >= MAX_S * rate) flush();
  };
  source.connect(tap);
  tap.connect(ctx.destination); // a processor only runs while it's connected
  stream.getAudioTracks()[0].addEventListener('ended', () => ended('the call tab stopped sharing its audio'));
  ears = { stream, ctx, flush };
}

function stop() {
  if (!ears) return;
  const { stream, ctx, flush } = ears;
  ears = null;
  flush(); // what was said since the last chunk
  stream.getTracks().forEach((t) => t.stop());
  ctx.close();
}

function ended(reason) {
  stop();
  chrome.runtime.sendMessage({ type: 'ears-ended', reason }).catch(() => {});
}

// ---- a chunk: resample, skip silence, wav, post ---------------------------
async function send(parts, from, agentId) {
  const samples = resample(concat(parts), from, RATE);
  if (!samples.length || rms(samples) < QUIET) return;
  const audio = await base64(wav(samples, RATE));
  await fetch(`${SERVER}/api/hear`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId, audio, mime: 'audio/wav' }),
  }).catch(() => {}); // renga's down: that chunk is lost, the next one tries again
}

function concat(parts) {
  const out = new Float32Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of parts) { out.set(p, at); at += p.length; }
  return out;
}

// Averages each output sample over the input samples it covers: a cheap
// low-pass, good enough for speech.
function resample(input, from, to) {
  if (from === to) return input;
  const ratio = from / to;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const a = Math.floor(i * ratio), b = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = a; j < b; j++) sum += input[j];
    out[i] = sum / Math.max(1, b - a);
  }
  return out;
}

function rms(samples) {
  let sum = 0;
  for (const s of samples) sum += s * s;
  return Math.sqrt(sum / samples.length);
}

// 16-bit pcm in a riff/wave header.
function wav(samples, rate) {
  const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
  const text = (at, s) => { for (let i = 0; i < s.length; i++) view.setUint8(at + i, s.charCodeAt(i)); };
  text(0, 'RIFF'); view.setUint32(4, 36 + samples.length * 2, true); text(8, 'WAVE');
  text(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); text(36, 'data'); view.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));
  return new Blob([view], { type: 'audio/wav' });
}

function base64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}
