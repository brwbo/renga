// sprite generator — the one copy. docs/sprites.html and docs/roster.html and
// web/app.js all load this file; nothing keeps a second copy of it.
// plain script, not an ES module: these pages open from file:// where imports are blocked.
(function(){
'use strict';
// ===== canvas grid: character space is 32x48 at (X0,Y0); canvas has margins for props =====
const W=44, H=54, X0=6, Y0=5;
const newG=()=>Array.from({length:H},()=>Array(W).fill('.'));
const px=(g,x,y,c)=>{ x+=X0; y+=Y0; if(y>=0&&y<H&&x>=0&&x<W) g[y][x]=c; };
const rect=(g,x,y,w,h,c)=>{ for(let j=y;j<y+h;j++) for(let i=x;i<x+w;i++) px(g,i,j,c); };
const stamp=(g,x,y,rows)=>rows.forEach((r,j)=>{ for(let i=0;i<r.length;i++){ const c=r[i]; if(c==='.') continue; px(g,x+i,y+j,c==='_'?'.':c); } });
const line=(g,x1,y1,x2,y2,c)=>{ const n=Math.max(Math.abs(x2-x1),Math.abs(y2-y1)); for(let i=0;i<=n;i++) px(g,Math.round(x1+(x2-x1)*i/n),Math.round(y1+(y2-y1)*i/n),c); };
function outline(g){ const o=g.map(r=>r.slice()); for(let y=0;y<H;y++) for(let x=0;x<W;x++){ if(g[y][x]!=='.') continue;
  if([[1,0],[-1,0],[0,1],[0,-1]].some(([dx,dy])=>{const yy=y+dy,xx=x+dx; return yy>=0&&yy<H&&xx>=0&&xx<W&&g[yy][xx]!=='.';})) o[y][x]='#'; } return o; }
const merge=(d,s)=>{ for(let y=0;y<H;y++) for(let x=0;x<W;x++) if(s[y][x]!=='.') d[y][x]=s[y][x]; };

// ===== palette: the shared ramp for the cloth, real colour for the person =====
// The seven ramp chars are the same ones the tiles use (palette.js), so a person
// stands in the same light as the room. 'p' 'q' 'z' are sprite-local props, and
// the five uppercase chars are the neon from palette.js — used the same way the
// city uses it, only ever for something that emits: a drawstring catching the
// screen glow, a hi-vis band, wet paint, a hard hat lamp.
const RAMP = (typeof window !== 'undefined' && window.PALETTE && window.PALETTE.BASE) || {
  '#':'#080a14','d':'#161c30','x':'#28334f','l':'#44567f','o':'#7d92bd','g':'#c2d2ee','w':'#f2f7ff' };
const NEON = (typeof window !== 'undefined' && window.PALETTE && window.PALETTE.NEON) || {
  'n':'#33e6ff','p':'#e619ac','y':'#ffb833','v':'#a64dff','b':'#4da6ff','G':'#39ff8f' };
// the ramp plus the sprite-local prop colours — the fallback palette other
// modules reach for when a tile char is not in TILE_PAL
const SPRITE_PAL = { ...RAMP, 'p':'#8a5a2b','q':'#6f7d99','z':'#8fd3ff',
  'N':NEON['n'], 'M':NEON['p'], 'Y':NEON['y'], 'V':NEON['v'], 'E':NEON['G'] };
const SKINS = [ ['#f7d9bd','#e2b596'], ['#ecc39e','#cf9a73'], ['#c98f5e','#a66d42'], ['#96603f','#71452b'], ['#5e3a26','#3f261a'] ];
const HAIRS = { black:['#101014','#2a2a33','#4a4a58'], brown:['#3a2314','#5c3a22','#8a5a38'], blonde:['#a67f35','#d8b25a','#f2d78e'], ginger:['#8a3a12','#b8561e','#e08a44'], grey:['#6c6c6c','#9b9b9b','#c9c9c9'], auburn:['#5a1f14','#8c3324','#c05a3a'] };
const ACCENTS = { red:['#8e1b1b','#d32f2f'], blue:['#123f80','#2467c9'], green:['#1b5e20','#2e9e3a'], gold:['#b8891f','#f2c14e'], purple:['#472a6e','#7b4bc0'], pink:['#a53a6f','#ec5fa8'], teal:['#0f5f5a','#1eaea3'] };
const EYES = { blue:'#2f5ea8', brown:'#4a2e1a', green:'#2f7d3a', hazel:'#8a6a2a', grey:'#5a6470' };
const MOUTH = '#a0524d';
function palette(spec){ const s=SKINS[spec.skin], h=HAIRS[spec.hair], a=ACCENTS[spec.accent];
  return {...SPRITE_PAL, s:s[0], t:s[1], k:h[0], h:h[1], j:h[2], a:a[1], b:a[0], e:EYES[spec.eyes], m:MOUTH}; }

// ===== outfits: what the job wears =====
// An agent should be readable at 2× on a tile, before you get to the name, so
// the outfit is the silhouette's job: cloth[base, lit, dark] sets the whole
// garment's tone, `chest` draws the thing that names the role, `legs` says what
// the trousers are, `tie` is true only for the one outfit a tie belongs on.
const OUTFITS = {
  // the suit is still the suit — the pm and the spender, nobody else
  suit:     { cloth:['x','l','d'], legs:['x','l','d'], cuff:'w', tie:true,  chest:'suit' },
  // dev hoodie: drawstrings lit by the screen, kangaroo pocket
  hoodie:   { cloth:['d','x','#'], legs:['x','l','d'], cuff:'x', chest:'hoodie' },
  // artist's apron: canvas bib, brush in the pocket, wet paint on it
  apron:    { cloth:['d','x','#'], legs:['x','l','d'], cuff:'x', chest:'apron' },
  // lab coat: open over a dark shirt, pens and a badge
  labcoat:  { cloth:['g','w','o'], legs:['d','x','#'], cuff:'w', chest:'labcoat' },
  // hi-vis over workwear, retroreflective bands, for the one who mines
  hivis:    { cloth:['x','l','d'], legs:['x','l','d'], cuff:'l', band:'Y', chest:'hivis' },
  // the clerk: waistcoat over shirtsleeves, watch chain
  visor:    { cloth:['g','w','o'], legs:['d','x','#'], cuff:'w', chest:'clerk' },
  // black turtleneck — the ones who decide and the one who audits
  turtle:   { cloth:['d','x','#'], legs:['d','x','#'], cuff:'x', chest:'turtle' },
  // coveralls with a name patch, for whoever takes what is left
  coverall: { cloth:['l','o','x'], legs:['l','o','x'], cuff:'o', chest:'coverall' },
};
const outfitOf = (name) => OUTFITS[name] || OUTFITS.suit;

// ===== layers =====
function legsLayer(mode, O){ const g=newG(); const off = mode==='apart' ? 1 : 0;
  const [B,L,D] = O.legs;
  rect(g,10-off,38,6,8,B); rect(g,16+off,38,6,8,B);
  for(let y=39;y<46;y++){ px(g,11-off,y,L); px(g,17+off,y,L); px(g,15-off,y,D); px(g,21+off,y,D); }
  if(O.band){ rect(g,10-off,42,6,1,O.band); rect(g,16+off,42,6,1,O.band); }
  rect(g,8-off,46,7,2,'d'); rect(g,17+off,46,7,2,'d'); px(g,9-off,46,'x'); px(g,18+off,46,'x');
  if(mode==='apart'){ rect(g,10-off,38,6,1,B); }
  return g; }
function headLayer(){ const g=newG();
  rect(g,10,4,12,13,'s'); rect(g,12,3,8,1,'s'); rect(g,12,17,8,1,'s');
  rect(g,20,5,2,12,'t'); rect(g,12,17,8,1,'t'); px(g,19,16,'t');
  rect(g,9,9,1,3,'s'); rect(g,22,9,1,3,'t');            // ears
  rect(g,13,18,6,3,'s'); rect(g,13,18,6,1,'t'); px(g,18,19,'t'); px(g,18,20,'t'); // neck
  return g; }
function hand(g,hx,hy,O){ rect(g,hx,hy-1,4,1,O.cuff); rect(g,hx,hy,4,3,'s'); px(g,hx+3,hy+1,'t'); px(g,hx+3,hy+2,'t'); px(g,hx+1,hy+2,'t'); }
function arm(g,side,mode,hp,O){ const x0 = side==='L' ? 4 : 24; const [B,L,D]=O.cloth;
  if(mode==='down'){ rect(g,x0,22,4,12,B); if(side==='L'){ for(let y=23;y<34;y++) px(g,x0,y,L); } else { for(let y=23;y<34;y++) px(g,x0+3,y,D); }
    hand(g,x0,35,O); }
  else if(mode==='forward'){ rect(g,x0,22,4,8,B); const [hx,hy]=hp; const fx=Math.min(x0,hx), fw=Math.abs(hx-x0)+4; rect(g,fx,hy-4,fw,3,B); if(side==='L') for(let x=fx;x<fx+fw;x++) px(g,x,hy-4,L); hand(g,hx,hy,O); }
  else if(mode==='up'){ rect(g,x0,11,4,12,B); if(side==='R'){ for(let y=12;y<23;y++) px(g,x0+3,y,D); } else { for(let y=12;y<23;y++) px(g,x0,y,L); } hand(g,x0,8,O); }
  else if(mode==='phone'){ rect(g,x0,22,4,8,B); const fx = side==='R' ? 22 : 6; rect(g,fx,13,4,17,B); for(let y=14;y<30;y++) px(g,fx+(side==='R'?3:0),y,D); hand(g,fx,10,O); }
}

// ---- the chest of each outfit: the one place the job is legible ----
const CHEST = {
  suit(g){
    // shirt V, lapels, edges  [row, shirtL, shirtR, lapL, lapR, edgeL, edgeR]
    const V=[[21,13,18,11,12,10,21],[22,13,18,11,12,10,21],[23,14,17,12,13,11,20],[24,14,17,12,13,11,20],[25,14,17,11,13,10,21],[26,14,17,11,13,10,21],[27,15,16,12,14,11,20],[28,15,16,12,14,11,20],[29,15,16,13,14,12,19]];
    for(const [r,sl,sr,ll,lr,el,er] of V){ for(let x=sl;x<=sr;x++) px(g,x,r, x>=16?'g':'w'); for(let x=ll;x<=lr;x++){ px(g,x,r,'d'); px(g,31-x,r,'d'); } px(g,el,r,'#'); px(g,er,r,'#'); }
    rect(g,12,20,2,1,'w'); rect(g,18,20,2,1,'g');                  // collar tips
    for(let y=30;y<38;y++) px(g,16,y,'#'); px(g,17,31,'o'); px(g,17,34,'o'); // seam + buttons
    rect(g,21,27,3,1,'a'); rect(g,21,28,3,1,'#');                   // pocket square
    rect(g,9,37,14,1,'#'); rect(g,15,37,2,1,'o');                   // belt + buckle
  },
  hoodie(g){
    rect(g,9,19,14,3,'x'); rect(g,10,20,12,1,'d'); rect(g,11,21,10,1,'#');   // hood bunched at the neck
    for(let y=22;y<37;y++){ px(g,16,y,'#'); px(g,17,y,'x'); }                 // zip
    for(let y=23;y<30;y++){ px(g,14,y,'N'); px(g,19,y,'N'); }                 // drawstrings, lit
    px(g,14,30,'w'); px(g,19,30,'w');
    rect(g,10,30,13,1,'#'); rect(g,11,31,11,4,'x');                           // kangaroo pocket
    for(let y=30;y<36;y++){ px(g,10,y,'#'); px(g,22,y,'#'); }
    rect(g,10,35,13,1,'#'); rect(g,8,36,16,2,'x');                            // hem band
  },
  apron(g){
    rect(g,13,21,6,2,'x'); px(g,12,21,'#'); px(g,19,21,'#');         // tee neckline
    for(let y=21;y<26;y++){ px(g,12,y,'o'); px(g,19,y,'o'); }        // straps over the shoulders
    rect(g,11,25,11,12,'g'); rect(g,11,25,11,1,'w');                 // canvas bib
    for(let y=26;y<37;y++){ px(g,21,y,'o'); px(g,11,y,'w'); }
    rect(g,8,30,16,1,'x'); px(g,7,31,'x'); px(g,24,31,'x');          // waist tie
    rect(g,12,32,9,4,'o'); rect(g,12,32,9,1,'x');                    // pocket
    for(let y=33;y<36;y++) px(g,16,y,'x');
    rect(g,20,26,1,2,'M'); px(g,20,28,'q'); rect(g,20,29,1,5,'p');   // brush, tip still wet
    px(g,13,27,'M'); px(g,14,28,'M'); px(g,17,26,'N');               // spatters — the only neon on it
    px(g,18,30,'Y'); px(g,13,35,'N'); px(g,15,36,'Y');
  },
  labcoat(g){
    rect(g,14,20,4,18,'d');                                          // dark shirt under the open coat
    for(let y=21;y<30;y++){ px(g,12,y,'w'); px(g,13,y,'w'); px(g,18,y,'w'); px(g,19,y,'w'); }  // lapels
    px(g,13,31,'o'); px(g,13,35,'o');                                // buttons
    rect(g,19,25,4,4,'o'); rect(g,19,25,4,1,'w');                    // breast pocket
    px(g,20,23,'N'); px(g,20,24,'N'); px(g,22,23,'M'); px(g,22,24,'M');  // pens
    rect(g,9,28,4,5,'w'); rect(g,9,28,4,1,'N');                      // id badge
    rect(g,10,30,2,1,'o'); px(g,10,31,'o');
  },
  hivis(g){
    rect(g,12,20,8,1,'l');                                           // collar of the jacket under it
    rect(g,9,21,14,17,'d');                                          // the vest
    rect(g,9,26,14,2,'Y'); rect(g,9,31,14,2,'Y');                    // retroreflective bands
    rect(g,11,21,2,5,'Y'); rect(g,19,21,2,5,'Y');                    // over each shoulder
    for(let y=21;y<38;y++){ px(g,16,y,'#'); px(g,15,y,'x'); }        // the vest opens
    rect(g,10,34,5,3,'x'); rect(g,10,34,5,1,'l');                    // pocket
    rect(g,18,34,4,3,'x'); rect(g,18,34,4,1,'l');
  },
  clerk(g){
    rect(g,13,20,6,2,'w');                                           // shirt collar
    rect(g,10,22,12,16,'d');                                         // waistcoat
    for(let y=22;y<38;y++){ px(g,10,y,'x'); px(g,21,y,'x'); }
    rect(g,14,21,4,7,'w'); rect(g,15,22,2,6,'a');                    // shirt and a thin tie
    px(g,16,29,'o'); px(g,16,32,'o'); px(g,16,35,'o');               // buttons
    px(g,11,30,'Y'); px(g,12,31,'Y'); px(g,13,32,'Y'); px(g,14,32,'Y');  // watch chain
    rect(g,9,37,14,1,'#');
  },
  turtle(g){
    rect(g,12,18,8,4,'x'); rect(g,12,18,8,1,'l');                    // rolled collar
    for(let y=19;y<22;y++) px(g,19,y,'#');
    rect(g,9,22,14,1,'#');                                           // shoulder seam
    for(let y=23;y<38;y++){ px(g,15,y,'#'); }                        // one long fold, nothing else
    px(g,12,26,'a'); px(g,12,27,'b');                                // a single pin
  },
  coverall(g){
    rect(g,11,20,10,2,'o'); rect(g,13,20,6,1,'x');                   // collar
    for(let y=21;y<38;y++){ px(g,16,y,'#'); px(g,17,y,'o'); }        // zip
    rect(g,10,24,5,4,'x'); rect(g,10,24,5,1,'o');                    // chest patches
    rect(g,11,25,3,2,'a');                                           // name patch
    rect(g,18,24,5,4,'x'); rect(g,18,24,5,1,'o');
    rect(g,8,32,16,2,'x'); px(g,15,32,'o'); px(g,15,33,'o');         // waist band
    px(g,21,35,'N'); px(g,21,36,'N');                                // a tool loop, lit
  },
};

function bodyLayer(pose, outfit){ const g=newG(); const O=outfitOf(outfit); const [B,L,D]=O.cloth;
  rect(g,6,21,20,1,B); rect(g,8,22,16,16,B);                      // shoulders + torso
  for(let y=22;y<38;y++){ px(g,8,y,L); px(g,9,y,L); px(g,22,y,D); px(g,23,y,D); }
  for(let y=24;y<35;y++){ px(g,7,y,D); px(g,24,y,D); }
  CHEST[O.chest](g);
  arm(g,'L',pose.armL||'down',pose.handL,O); arm(g,'R',pose.armR||'down',pose.handR,O);
  return g; }
function hairLayer(style){ const g=newG();
  const top=()=>{ rect(g,11,0,10,1,'h'); rect(g,9,1,14,4,'h'); rect(g,10,1,4,1,'j'); rect(g,9,2,1,3,'j'); };
  if(style==='parted'){ top(); rect(g,9,5,5,1,'h'); rect(g,9,6,3,1,'h'); rect(g,9,7,1,3,'h'); rect(g,22,5,1,4,'h'); for(let y=1;y<5;y++) px(g,15,y,'k'); rect(g,16,1,6,4,'k'); rect(g,16,1,5,1,'h'); }
  else if(style==='buzz'){ rect(g,12,1,8,1,'k'); rect(g,10,2,12,3,'k'); rect(g,10,5,12,1,'h'); rect(g,9,5,1,4,'k'); rect(g,22,5,1,4,'k'); rect(g,11,2,3,1,'h'); }
  else if(style==='long'){ top(); rect(g,9,5,4,1,'h'); rect(g,8,5,2,13,'h'); rect(g,22,5,2,13,'h'); rect(g,7,10,1,10,'h'); rect(g,24,10,1,10,'h'); rect(g,8,6,1,6,'j'); rect(g,23,6,1,12,'k'); rect(g,7,18,3,2,'k'); rect(g,22,18,3,2,'k'); }
  else if(style==='bob'){ top(); rect(g,9,5,13,2,'h'); rect(g,10,6,11,1,'k'); rect(g,8,5,2,8,'h'); rect(g,22,5,2,8,'h'); rect(g,8,6,1,5,'j'); rect(g,23,6,1,7,'k'); }
  else if(style==='curly'){ rect(g,10,0,12,1,'h'); rect(g,8,1,16,5,'h'); rect(g,8,6,2,4,'h'); rect(g,22,6,2,4,'h'); for(let y=0;y<7;y++) for(let x=8;x<24;x++) if((x+y)%3===0) px(g,x,y,'k'); for(let x=9;x<23;x+=4) px(g,x,1,'j'); px(g,9,7,'k'); px(g,22,8,'k'); }
  else if(style==='bun'){ rect(g,12,1,8,1,'h'); rect(g,10,2,12,3,'h'); rect(g,10,5,12,1,'k'); rect(g,9,5,1,4,'h'); rect(g,22,5,1,3,'h'); rect(g,20,-1,5,4,'h'); rect(g,21,0,3,2,'k'); px(g,21,-1,'j'); rect(g,11,2,3,1,'j'); }
  else if(style==='bald'){ rect(g,9,6,1,4,'h'); rect(g,22,6,1,4,'h'); rect(g,9,7,2,2,'h'); rect(g,21,7,2,2,'h'); }
  return g; }
function faceDetails(g,spec,pose){
  rect(g,11,7,4,1,'k'); rect(g,17,7,4,1,'k');                    // brows
  const eyes=pose.eyes||'open';
  if(eyes==='open'||eyes==='down'){ for(const ex of [11,17]){ rect(g,ex,9,4,2,'w'); if(eyes==='open'){ px(g,ex+1,9,'e'); px(g,ex+2,9,'e'); px(g,ex+1,10,'#'); px(g,ex+2,10,'#'); }
      else { const s=pose.look||0; px(g,ex+1+s,10,'e'); px(g,ex+2+s,10,'#'); px(g,ex+1+s,9,'e'); } } }
  else if(eyes==='closed'){ rect(g,12,10,2,1,'#'); rect(g,18,10,2,1,'#'); }
  px(g,16,12,'t'); px(g,15,13,'t'); px(g,16,13,'t');              // nose
  const mouth=pose.mouth||'neutral';
  if(mouth==='neutral') rect(g,14,14,4,1,'m');
  else if(mouth==='open'){ rect(g,14,14,4,1,'#'); rect(g,14,15,4,1,'m'); }
  else if(mouth==='frown'){ px(g,14,14,'m'); px(g,17,14,'m'); rect(g,15,15,2,1,'m'); }
  else if(mouth==='smile'){ px(g,13,13,'m'); px(g,18,13,'m'); rect(g,14,14,4,1,'m'); }
}
function faceAcc(kind){ const g=newG();
  if(kind==='glasses'){ for(const x0 of [10,16]){ rect(g,x0,8,6,1,'#'); rect(g,x0,11,6,1,'#'); rect(g,x0,9,1,2,'#'); rect(g,x0+5,9,1,2,'#'); } px(g,9,9,'#'); px(g,22,9,'#'); }
  else if(kind==='shades'){ rect(g,10,8,6,4,'#'); rect(g,16,8,6,4,'#'); px(g,11,9,'x'); px(g,17,9,'x'); px(g,9,9,'#'); px(g,22,9,'#'); }
  else if(kind==='tache'){ rect(g,13,13,6,1,'k'); px(g,12,14,'k'); px(g,19,14,'k'); }
  else if(kind==='beard'){ rect(g,13,13,6,1,'k'); rect(g,10,13,2,1,'k'); rect(g,20,13,2,1,'k'); rect(g,10,14,3,1,'k'); rect(g,19,14,3,1,'k'); rect(g,10,15,12,1,'k'); rect(g,11,16,10,1,'k'); rect(g,12,17,8,1,'k'); rect(g,13,18,6,1,'k'); rect(g,11,15,2,1,'h'); }
  return g; }
// ---- headgear: drawn over the hair, because that is where a hat goes ----
function hatLayer(kind){ const g=newG();
  if(kind==='beret'){ rect(g,10,0,11,1,'a'); rect(g,9,1,14,3,'a'); rect(g,17,2,6,2,'b'); rect(g,9,4,14,1,'b'); px(g,22,0,'a'); px(g,23,1,'a'); px(g,11,1,'w'); }
  else if(kind==='hardhat'){ rect(g,15,-2,2,2,'p'); rect(g,10,-1,12,1,'Y'); rect(g,9,0,14,5,'Y'); rect(g,19,1,4,4,'p');
    rect(g,7,5,18,2,'Y'); rect(g,7,6,18,1,'p'); rect(g,13,1,6,3,'q'); rect(g,14,2,4,1,'N'); px(g,15,0,'N'); px(g,17,0,'N'); }
  else if(kind==='eyeshade'){ rect(g,9,2,14,1,'d'); rect(g,8,3,16,3,'E'); rect(g,8,6,16,1,'#'); px(g,10,3,'w'); px(g,11,3,'w'); px(g,8,2,'d'); px(g,23,2,'d'); }
  else if(kind==='cap'){ rect(g,11,0,10,1,'a'); rect(g,10,1,12,4,'a'); rect(g,17,2,5,3,'b'); rect(g,9,5,14,1,'b');
    rect(g,4,5,6,2,'b'); rect(g,4,5,6,1,'a'); px(g,15,1,'w'); }
  return g; }
function tieLayer(kind){ const g=newG();
  if(kind==='tie'){ rect(g,14,20,4,2,'a'); px(g,17,20,'b'); px(g,17,21,'b'); rect(g,15,22,2,8,'a'); for(let y=22;y<30;y++) px(g,16,y,'b'); px(g,15,29,'b'); }
  else if(kind==='bowtie'){ rect(g,12,20,3,1,'a'); rect(g,17,20,3,1,'a'); rect(g,12,21,8,1,'a'); rect(g,12,22,3,1,'b'); rect(g,17,22,3,1,'b'); rect(g,15,21,2,1,'b'); px(g,14,21,'b'); }
  return g; }
function extraLayer(kind){ const g=newG();
  if(kind==='headset'){ rect(g,10,1,12,1,'d'); rect(g,7,8,3,5,'d'); rect(g,22,8,3,5,'d'); px(g,8,9,'l'); px(g,23,9,'l'); rect(g,21,13,2,1,'d'); px(g,20,14,'d'); rect(g,19,15,2,1,'d'); px(g,18,15,'o'); }
  else if(kind==='coffee'){ rect(g,25,32,4,4,'w'); rect(g,25,34,4,1,'a'); px(g,29,33,'#'); px(g,29,34,'#'); px(g,26,29,'o'); px(g,27,30,'o'); px(g,26,31,'o'); }
  else if(kind==='briefcase'){ rect(g,1,38,6,6,'d'); rect(g,2,37,3,1,'d'); rect(g,1,40,6,1,'x'); px(g,3,41,'o'); px(g,4,41,'o'); px(g,2,39,'l'); }
  else if(kind==='lanyard'){ for(let y=21;y<31;y++){ px(g,12,y,'a'); px(g,19,y,'a'); } rect(g,13,30,6,4,'w'); rect(g,14,31,2,2,'t'); rect(g,17,31,1,1,'o'); rect(g,17,32,1,1,'o'); }
  return g; }

// ===== props for work animations (own layers, outlined) =====
function propLaptopKeys(){ const g=newG(); rect(g,6,35,20,2,'o'); for(let x=7;x<26;x+=2) px(g,x,35,'d'); return g; }
function propBook(frame){ const g=newG(); rect(g,9,26,14,9,'w'); rect(g,15,26,2,9,'d'); rect(g,9,34,14,1,'a');
  for(let y=28;y<34;y+=2){ rect(g,10,y,4,1,'o'); rect(g,18,y,4,1,'o'); } if(frame===1){ rect(g,17,25,4,3,'w'); rect(g,17,25,4,1,'g'); } return g; }
function propPick(frame){ const g=newG(); if(frame===0){ line(g,26,7,34,-1,'p'); line(g,27,7,35,-1,'p'); rect(g,32,-4,6,3,'q'); rect(g,33,-3,4,1,'l'); }
  else { line(g,27,36,36,41,'p'); line(g,27,37,36,42,'p'); rect(g,35,40,5,5,'q'); rect(g,36,41,3,1,'l'); rect(g,31,44,9,4,'x'); px(g,34,45,'a'); px(g,35,46,'a'); px(g,33,46,'d'); px(g,30,42,'j'); px(g,38,38,'j'); } return g; }
function propPad(frame){ const g=newG(); rect(g,18,33,9,4,'w'); rect(g,18,33,9,1,'o'); rect(g,19,35,6,1,'o'); const dx=frame; line(g,21+dx,29,23+dx,33,'a'); px(g,23+dx,33,'#'); return g; }
function propPhone(){ const g=newG(); rect(g,23,8,3,7,'d'); rect(g,24,9,1,5,'e'); px(g,24,14,'o'); return g; }
function propGlass(frame){ const g=newG(); const dx=frame; rect(g,21+dx,6,6,6,'z'); rect(g,22+dx,7,4,4,'z'); px(g,22+dx,7,'w'); px(g,23+dx,7,'w'); line(g,26+dx,12,29+dx,16,'p'); return g; }
function propCoins(frame){ const g=newG(); rect(g,4,34,24,3,'o'); for(let i=0;i<5;i++){ rect(g,7+i*4,31-(i%2)-(frame&&i==2?1:0),3,3,'a'); px(g,8+i*4,32-(i%2)-(frame&&i==2?1:0),'b'); } return g; }
function propSpeech(frame){ const g=newG(); rect(g,23,-4,9,5,'w'); px(g,24,1,'w'); const c = frame ? 'k':'o'; px(g,25,-2,frame?'#':'o'); px(g,27,-2,frame?'o':'#'); px(g,29,-2,frame?'#':'o'); return g; }
function stampZ(g,frame){ const z=['###','..#','.#.','#..','###']; stamp(g, frame? 27:25, frame? -5:-2, z); if(frame) stamp(g,24,2,['##','.#','#.','##']); }
function stampQ(g){ stamp(g,27,-5,['.###.','#...#','....#','...#.','..#..','.....','..#..']); }
function stampSweat(g,frame){ const y=6+frame; px(g,24,y,'z'); px(g,23,y+1,'z'); px(g,24,y+1,'z'); px(g,25,y+1,'z'); px(g,24,y+2,'z'); px(g,24,y+1,'w'); }

// ===== poses per state and per work style =====
function pose(spec, state, frame){
  const f=frame%2; const p={eyes:'open',mouth:'neutral',legs:'stand',armL:'down',armR:'down',props:[],after:[]};
  if(state==='idle') return p;
  if(state==='sleep'){ p.eyes='closed'; p.after.push(g=>stampZ(g,f)); return p; }
  if(state==='talk'){ p.mouth = f?'open':'neutral'; p.props.push(propSpeech(f)); return p; }
  if(state==='walk'){ p.legs = f?'apart':'stand'; return p; }
  if(state==='wait'){ p.armR='up'; p.mouth='smile'; if(f) p.after.push(stampQ); return p; }
  if(state==='error'){ p.mouth='frown'; p.eyes='down'; p.after.push(g=>stampSweat(g,f)); return p; }
  if(state==='work'){ const w=spec.work||'typing';
    if(w==='typing'){ p.armL='forward'; p.armR='forward'; p.handL=[9,32+f]; p.handR=[19,33-f]; p.eyes='down'; p.look=f; p.props.push(propLaptopKeys()); }
    else if(w==='reading'){ p.armL='forward'; p.armR='forward'; p.handL=[7,31]; p.handR=[22,31]; p.eyes='down'; p.look=f; p.props.push(propBook(frame%4===3?1:0)); }
    else if(w==='mining'){ p.armR = f?'down':'up'; p.mouth = f?'open':'neutral'; p.props.push(propPick(f)); }
    else if(w==='writing'){ p.armL='forward'; p.armR='forward'; p.handL=[13,32]; p.handR=[19+f,31]; p.eyes='down'; p.props.push(propPad(f)); }
    else if(w==='phone'){ p.armR='phone'; p.mouth = f?'open':'neutral'; p.props.push(propPhone()); }
    else if(w==='inspect'){ p.armR='phone'; p.eyes='open'; p.props.push(propGlass(f)); }
    else if(w==='counting'){ p.armL='forward'; p.armR='forward'; p.handL=[8,31-f]; p.handR=[20,31+f]; p.eyes='down'; p.look=f; p.props.push(propCoins(f)); }
  }
  return p; }

function build(spec, state, frame){ const P=pose(spec,state,frame); const out=newG();
  const outfit = spec.outfit || 'suit', O = outfitOf(outfit);
  merge(out, outline(legsLayer(P.legs, O)));
  merge(out, outline(headLayer()));
  merge(out, outline(bodyLayer(P, outfit)));
  faceDetails(out, spec, P);
  merge(out, outline(hairLayer(spec.style)));
  if(spec.face && spec.face!=='none') merge(out, outline(faceAcc(spec.face)));
  if(O.tie) merge(out, outline(tieLayer(spec.tie||'tie')));
  if(spec.hat && spec.hat!=='none') merge(out, outline(hatLayer(spec.hat)));
  if(spec.extra && spec.extra!=='none') merge(out, outline(extraLayer(spec.extra)));
  for(const pr of P.props) merge(out, outline(pr));
  for(const fn of P.after) fn(out);
  return out; }
function draw(ctx, g, scale, pal, ox=0, oy=0){ for(let y=0;y<H;y++) for(let x=0;x<W;x++){ const c=g[y][x]; if(c==='.') continue; ctx.fillStyle = pal[c] || '#ff00ff'; ctx.fillRect(ox+x*scale, oy+y*scale, scale, scale); } }

// ===== cast: one of each outfit, so the page shows the whole wardrobe =====
const CAST = [
  {name:'pm', skin:1, hair:'black', style:'parted', accent:'red', eyes:'brown', tie:'tie', face:'none', extra:'none', outfit:'suit', hat:'none', work:'phone'},
  {name:'backend', skin:3, hair:'black', style:'buzz', accent:'blue', eyes:'brown', tie:'tie', face:'glasses', extra:'none', outfit:'hoodie', hat:'none', work:'typing'},
  {name:'frontend', skin:0, hair:'blonde', style:'bob', accent:'pink', eyes:'blue', tie:'bowtie', face:'none', extra:'lanyard', outfit:'hoodie', hat:'none', work:'typing'},
  {name:'documenter', skin:2, hair:'brown', style:'bun', accent:'green', eyes:'hazel', tie:'tie', face:'glasses', extra:'none', outfit:'visor', hat:'eyeshade', work:'writing'},
  {name:'spender', skin:1, hair:'grey', style:'bald', accent:'gold', eyes:'grey', tie:'tie', face:'tache', extra:'briefcase', outfit:'suit', hat:'none', work:'counting'},
  {name:'memecoin', skin:4, hair:'black', style:'curly', accent:'purple', eyes:'brown', tie:'tie', face:'none', extra:'headset', outfit:'hivis', hat:'hardhat', work:'mining'},
  {name:'tester', skin:0, hair:'ginger', style:'long', accent:'teal', eyes:'green', tie:'tie', face:'none', extra:'coffee', outfit:'labcoat', hat:'none', work:'inspect'},
  {name:'researcher', skin:2, hair:'auburn', style:'parted', accent:'blue', eyes:'green', tie:'bowtie', face:'beard', extra:'none', outfit:'labcoat', hat:'none', work:'reading'},
  {name:'pixel artist', skin:3, hair:'black', style:'curly', accent:'pink', eyes:'brown', tie:'tie', face:'none', extra:'coffee', outfit:'apron', hat:'beret', work:'writing'},
  {name:'art director', skin:2, hair:'grey', style:'bun', accent:'purple', eyes:'grey', tie:'bowtie', face:'glasses', extra:'lanyard', outfit:'turtle', hat:'beret', work:'phone'},
  {name:'intern', skin:1, hair:'brown', style:'curly', accent:'gold', eyes:'blue', tie:'tie', face:'shades', extra:'coffee', outfit:'coverall', hat:'cap', work:'typing'},
];

window.Sprites = { W, H, build, draw, palette, CAST, RAMP, PAL: SPRITE_PAL,
  MONO: SPRITE_PAL,           // old name, kept so nothing downstream breaks
  OUTFITS, HATS: ['none','beret','hardhat','eyeshade','cap'],
  SKINS, HAIRS, ACCENTS, EYES };
})();
