// ColourFit - simple colour scheme generator and avatar applicator

// Utility: hex <-> HSL conversions
function hexToRgb(hex) {
  hex = hex.replace('#','');
  if (hex.length === 3) hex = hex.split('').map(c=>c+c).join('');
  const bigint = parseInt(hex,16);
  return { r: (bigint>>16)&255, g: (bigint>>8)&255, b: bigint&255 };
}
function rgbToHex({r,g,b}) {
  const toHex = v => v.toString(16).padStart(2,'0');
  return '#'+toHex(r)+toHex(g)+toHex(b);
}
function rgbToHsl({r,g,b}) {
  r/=255; g/=255; b/=255;
  const max = Math.max(r,g,b), min = Math.min(r,g,b);
  let h=0, s=0, l=(max+min)/2;
  if (max!==min) {
    const d = max-min;
    s = l>0.5 ? d/(2-max-min) : d/(max+min);
    switch(max){
      case r: h = (g-b)/d + (g<b ? 6:0); break;
      case g: h = (b-r)/d + 2; break;
      case b: h = (r-g)/d + 4; break;
    }
    h/=6;
  }
  return { h: Math.round(h*360), s: Math.round(s*100), l: Math.round(l*100) };
}
function hslToRgb({h,s,l}) {
  h = ((h%360)+360)/360; s/=100; l/=100;
  if (s===0) {
    const v = Math.round(l*255);
    return {r:v,g:v,b:v};
  }
  const q = l < 0.5 ? l*(1+s) : l + s - l*s;
  const p = 2*l - q;
  const hue2rgb = (p,q,t)=>{
    if (t<0) t+=1;
    if (t>1) t-=1;
    if (t<1/6) return p + (q-p)*6*t;
    if (t<1/2) return q;
    if (t<2/3) return p + (q-p)*(2/3 - t)*6;
    return p;
  };
  const r = Math.round(hue2rgb(p,q,h+1/3)*255);
  const g = Math.round(hue2rgb(p,q,h)*255);
  const b = Math.round(hue2rgb(p,q,h-1/3)*255);
  return {r,g,b};
}
function hslToHex(hsl){ return rgbToHex(hslToRgb(hsl)); }
function hexToHsl(hex){ return rgbToHsl(hexToRgb(hex)); }

// Scheme generation
function generateScheme(hex, mode) {
  const base = hexToHsl(hex);
  const h = base.h, s = base.s, l = base.l;
  const results = [];
  if (mode === 'complementary') {
    results.push(hslToHex({h: (h+180)%360, s, l}));
    results.push(hslToHex({h: (h+150)%360, s, l}));
  } else if (mode === 'analogous') {
    results.push(hslToHex({h: (h+30)%360, s, l}));
    results.push(hslToHex({h: (h-30+360)%360, s, l}));
  } else if (mode === 'triadic') {
    results.push(hslToHex({h: (h+120)%360, s, l}));
    results.push(hslToHex({h: (h+240)%360, s, l}));
  } else if (mode === 'monochrome') {
    results.push(hslToHex({h, s, l: Math.max(10, l-20)}));
    results.push(hslToHex({h, s, l: Math.min(90, l+20)}));
  }
  // include base as first
  return [hex, ...results];
}

// DOM wiring
const baseColorInput = document.getElementById('baseColor');
const baseHexInput = document.getElementById('baseHex');
const schemeSelect = document.getElementById('schemeSelect');
const suggestBtn = document.getElementById('suggestBtn');
const swatchContainer = document.getElementById('swatchContainer');
const savePaletteBtn = document.getElementById('savePaletteBtn');
const savedPalettes = document.getElementById('savedPalettes');

function getSelectedPart() {
  return document.querySelector('input[name="part"]:checked').value;
}

function applyColorToPart(partId, color) {
  const el = document.getElementById(partId);
  if (!el) return;
  // set fill on children paths/shape elements
  el.querySelectorAll('*').forEach(child => {
    if (child.hasAttribute('fill')) child.setAttribute('fill', color);
  });
  // also try the group itself
  if (el.hasAttribute('fill')) el.setAttribute('fill', color);
}

// render swatches
function showSwatches(colors) {
  swatchContainer.innerHTML = '';
  colors.forEach(hex => {
    const sw = document.createElement('button');
    sw.className = 'swatch';
    sw.style.background = hex;
    sw.setAttribute('aria-label', hex);
    sw.title = hex;
    sw.addEventListener('click', ()=> {
      const part = getSelectedPart();
      applyColorToPart(part, hex);
    });
    swatchContainer.appendChild(sw);
  });
}

// sync hex + color input
baseColorInput.addEventListener('input', e => {
  baseHexInput.value = e.target.value;
});
baseHexInput.addEventListener('input', e => {
  let v = e.target.value.trim();
  if (!v.startsWith('#')) v = '#'+v;
  if (/^#[0-9a-fA-F]{6}$/.test(v)) {
    baseColorInput.value = v;
  }
  e.target.value = v.slice(0,7);
});

// suggestions
suggestBtn.addEventListener('click', ()=>{
  const hex = baseHexInput.value;
  if (!/^#[0-9a-fA-F]{6}$/.test(hex)) {
    alert('Enter a valid 6-digit hex like #33aaee');
    return;
  }
  const scheme = schemeSelect.value;
  const colors = generateScheme(hex, scheme);
  showSwatches(colors);
});

// save palette (localStorage)
function loadSaved() {
  savedPalettes.innerHTML = '';
  const raw = localStorage.getItem('colourfit_palettes') || '[]';
  const arr = JSON.parse(raw);
  arr.forEach((pal, idx) => {
    const div = document.createElement('div');
    div.className = 'saved-palette';
    pal.forEach(hex => {
      const mini = document.createElement('div');
      mini.className = 'mini-swatch';
      mini.style.background = hex;
      mini.title = hex;
      div.appendChild(mini);
    });
    const loadBtn = document.createElement('button');
    loadBtn.textContent = 'Load';
    loadBtn.addEventListener('click', ()=> {
      showSwatches(pal);
    });
    const delBtn = document.createElement('button');
    delBtn.textContent = 'Delete';
    delBtn.addEventListener('click', ()=>{
      arr.splice(idx,1);
      localStorage.setItem('colourfit_palettes', JSON.stringify(arr));
      loadSaved();
    });
    div.appendChild(loadBtn);
    div.appendChild(delBtn);
    savedPalettes.appendChild(div);
  });
}

savePaletteBtn.addEventListener('click', ()=>{
  const colors = Array.from(swatchContainer.children).map(sw=> {
    const hex = sw.title || sw.getAttribute('aria-label');
    return hex;
  }).filter(Boolean);
  if (colors.length===0) {
    alert('No suggestions to save — click Suggest first.');
    return;
  }
  const raw = localStorage.getItem('colourfit_palettes') || '[]';
  const arr = JSON.parse(raw);
  arr.push(colors);
  localStorage.setItem('colourfit_palettes', JSON.stringify(arr));
  loadSaved();
});

// initialize with defaults
(function init(){
  const defaultHex = '#2b7a78';
  baseColorInput.value = defaultHex;
  baseHexInput.value = defaultHex;
  const initial = generateScheme(defaultHex, 'complementary');
  showSwatches(initial);
  loadSaved();
  // initial avatar colours retained from HTML
})();
