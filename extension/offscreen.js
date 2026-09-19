// the listener's ears when the call has no captions. an offscreen page
// (manifest v3 records audio only in one): it records the meet tab the
// panel picked, keeps playing it so you still hear the call, and every
// CHUNK_S seconds posts what was said as a 16 kHz mono wav to renga, which
// has gemini transcribe it as the listener. chunks with nobody talking are
// never sent.
'use strict';

const SERVER = 'http://localhost:8020';
const CHUNK_S = 8;    // how far behind the transcript runs, at least
const RATE = 16000;   // plenty for speech, and a third of the size of 48 kHz
const QUIET = 0.008;  // rms below this all chunk long: nobody spoke

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
  const tap = ctx.createScriptProcessor(4096, 1, 1);
  let buf = [];
  tap.onaudioprocess = (e) => {
    buf.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    e.outputBuffer.getChannelData(0).fill(0); // the tap itself stays silent
  };
  source.connect(tap);
  tap.connect(ctx.destination); // a processor only runs while it's connected
  const flush = () => { const chunk = buf; buf = []; send(chunk, ctx.sampleRate, agentId); };
  const timer = setInterval(flush, CHUNK_S * 1000);
  stream.getAudioTracks()[0].addEventListener('ended', () => ended('the call tab stopped sharing its audio'));
  ears = { stream, ctx, timer, flush };
}

function stop() {
  if (!ears) return;
  const { stream, ctx, timer, flush } = ears;
  ears = null;
  clearInterval(timer);
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
