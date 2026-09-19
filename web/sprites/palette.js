// web/sprites/palette.js — the one palette for renga (carried over from agentville).
// Works as a plain browser script (sets window.TILE_PAL and window.PALETTE) and
// as a Node module, so the tile generators and the pages cannot drift apart.
//
// The town is a cyberpunk city at night. The seven ramp chars are no longer
// greys: they run from near-black ink through cool indigo structure up to a
// cold ice highlight, so unlit mass reads as night and lit mass reads as
// window light. On top of that sit six NEON accents — the only saturated
// colour in the environment, and only ever used for things that emit light:
// signage, tube lighting, screen glow, a team's emblem.
//
// Chars are shared with the sprites so the two never fight: '# d x l o g w'
// is the ramp everything is built from, and 'n p y v b G' are the tubes.
(function (root) {
  'use strict';

  var BASE = {
    '#': '#080a14',   // ink, outlines — the black a neon sign sits on
    'd': '#161c30',   // deep shadow, unlit interior mass
    'x': '#28334f',   // shadow, dither partner for d
    'l': '#44567f',   // mid, the main structural tone
    'o': '#7d92bd',   // light, lit faces and rim light
    'g': '#c2d2ee',   // highlight, dither partner for w
    'w': '#f2f7ff'    // brightest, window light and hot edges
  };

  // Tubes. Saturated, emissive, never used for structure — only for light.
  var NEON = {
    'n': '#33e6ff',   // cyan    — servers, labs, cold machinery
    'p': '#e619ac',   // magenta — studios, bars, anything social
    'y': '#ffb833',   // amber   — offices, archives, the mine
    'v': '#a64dff',   // violet  — the vault, money, custody
    'b': '#4da6ff',   // blue    — reading rooms, research
    'G': '#39ff8f'    // green   — terminals, go signals, health
  };

  // Which tube a room burns. Read by the tile generators and by map.js.
  var ROOM_NEON = {
    pm: 'y', backend: 'n', frontend: 'p', documenter: 'y', spender: 'v',
    memecoin: 'y', tester: 'n', researcher: 'b', intern: 'p',
    generic: 'b', breakroom: 'p'
  };

  var PAL = {};
  var k;
  for (k in BASE) PAL[k] = BASE[k];
  for (k in NEON) PAL[k] = NEON[k];

  var API = { BASE: BASE, NEON: NEON, ROOM_NEON: ROOM_NEON, PAL: PAL,
    NEON_KEYS: ['n', 'p', 'y', 'v', 'b', 'G'] };

  if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
  else {
    root.PALETTE = API;
    root.TILE_PAL = root.TILE_PAL || {};
    for (k in PAL) root.TILE_PAL[k] = PAL[k];
  }
})(typeof window !== 'undefined' ? window : globalThis);
