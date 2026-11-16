#!/usr/bin/env python3
"""Render the STUDIO424 pedal skin (art + TUI.json + Q-Links.json) into ../skins/.

Run:  python3 plugins/STUDIO424/art/make_skin.py
Needs Google Chrome (headless screenshots) and Pillow.

The geometry, colours and gradients come from the "Stompbox" screen mockup
(1280 x 628 tab area). Each layer is drawn as HTML/SVG and screenshotted:

  bg.png          static enclosure, panel, knob wells, fader slot, labels
  knob.png        knob body + pointer, 127 frames of 72 x 84
  fader.png       fader cap over its travel, 127 frames of 68 x 312
"""
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "skins"))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

ACCENT = "#f2a277"
WORDMARK = "STUDIO424"

# Parameter indices (must match src/Plugin424.cpp).
P_CHANNEL, P_TRIM, P_HIGH, P_LOW, P_MASTER = range(5)

# Knobs: (label, param, x, y) in the mockup's panel coordinates.
KNOBS = [
    ("Trim",    P_TRIM,    60, 14),
    ("High",    P_HIGH,    60, 132),
    ("Low",     P_LOW,     60, 250),
    ("Channel", P_CHANNEL, 60, 368),
]

FACE = (440, 18)
PANEL = (FACE[0] + 22, FACE[1] + 62)
KNOB_W, KNOB_H, KNOB_FRAMES = 72, 84, 127
FADER_FRAMES = 127
PANEL_H = 500                      # panel fills the face (no footswitch section)
# Fader block spans the knob column: well top level with the top knob, MASTER
# label level with the bottom knob's label. Panel coordinates.
FADER_DY = 0
FADER_DX = -36                     # fader block shifted left, closer to the knobs
WELL_TOP, WELL_H = 34, 410
SLOT_TOP, SLOT_H = WELL_TOP + 24, WELL_H - 48
LINE_MAX, LINE_MIN = SLOT_TOP + 22, SLOT_TOP + SLOT_H - 32   # cap value line at 10 and at 0
FADER_LABEL_TOP = 456
FADER_BOX = (PANEL[0] + 271 + FADER_DX, PANEL[1] + 16, 68, 432)   # x y w h of the fader strip frame


def knob_pos(k):
    _, _, x, y = k
    return (PANEL[0] + x + 14, PANEL[1] + y)


def fader_top(v):
    return round(LINE_MIN - v * (LINE_MIN - LINE_MAX) - 42)


# ---------------------------------------------------------------------------
# HTML for the tab area. `show` picks layers: static, knob, fader.
# ---------------------------------------------------------------------------
HEAD = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Titillium+Web:wght@400;600;700&family=Orbitron:wght@800;900&display=block" rel="stylesheet">
<style>html,body{margin:0;background:transparent}*{box-sizing:content-box}
.tab{position:relative;width:1280px;height:628px;font-family:'Titillium Web',sans-serif}
.cam{position:relative;overflow:hidden}
.lbl{font-size:15px;line-height:18px;font-weight:700;color:#3a3a3a;text-transform:uppercase;text-shadow:0 1px 0 rgba(255,255,255,0.45);white-space:nowrap}
</style></head><body>"""

KNOB_DEFS = """<defs>
<radialGradient id="pkWell" cx="0.5" cy="0.4" r="0.6"><stop offset="0.7" stop-color="#a7a49d"/><stop offset="1" stop-color="#d6d3cb"/></radialGradient>
<radialGradient id="pkTop" cx="0.4" cy="0.35" r="0.7"><stop offset="0" stop-color="#8a8781"/><stop offset="1" stop-color="#6e6b66"/></radialGradient>
<linearGradient id="pkRim" x1="0.2" y1="0.1" x2="0.8" y2="0.9"><stop offset="0" stop-color="#a8a59f"/><stop offset="0.5" stop-color="#6c6964"/><stop offset="1" stop-color="#3e3c38"/></linearGradient>
<linearGradient id="pkBevel" x1="0.2" y1="0.1" x2="0.8" y2="0.9"><stop offset="0" stop-color="#ffffff" stop-opacity="0.45"/><stop offset="0.5" stop-color="#ffffff" stop-opacity="0"/><stop offset="1" stop-color="#000000" stop-opacity="0.35"/></linearGradient>
<filter id="pkBlur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3.5"/></filter>
</defs>"""

TICKS = """<g stroke="#f4f2ec" stroke-width="2" stroke-linecap="round"><line x1="9.8" y1="72.2" x2="5.6" y2="76.4"/><line x1="0.8" y1="57.4" x2="-4.9" y2="59.3"/><line x1="-0.5" y1="40.2" x2="-6.5" y2="39.3"/><line x1="6.1" y1="24.3" x2="1.2" y2="20.7"/><line x1="19.2" y1="13.0" x2="16.5" y2="7.7"/><line x1="36.0" y1="9.0" x2="36.0" y2="3.0"/><line x1="52.8" y1="13.0" x2="55.5" y2="7.7"/><line x1="65.9" y1="24.3" x2="70.8" y2="20.7"/><line x1="72.5" y1="40.2" x2="78.5" y2="39.3"/><line x1="71.2" y1="57.4" x2="76.9" y2="59.3"/><line x1="62.2" y1="72.2" x2="66.4" y2="76.4"/></g>"""


def knob_svg(angle, static, dynamic):
    s = [f'<svg width="72" height="84" viewBox="0 0 72 84" style="position:absolute;left:0;top:0;overflow:visible">', KNOB_DEFS]
    if static:
        s.append(TICKS)
        s.append('<circle cx="36" cy="46" r="33" fill="url(#pkWell)"/>'
                 '<circle cx="36" cy="46" r="31" fill="none" stroke="#8a8780" stroke-width="1"/>'
                 '<circle cx="36" cy="47" r="27.5" fill="#2c2b29"/>'
                 '<circle cx="41" cy="52" r="24" fill="#000" opacity="0.6" filter="url(#pkBlur)"/>'
                 '<circle cx="38" cy="48.5" r="24" fill="#000" opacity="0.5"/>')
    if dynamic:
        s.append('<circle cx="36" cy="46" r="24.5" fill="url(#pkRim)"/>'
                 f'<g transform="rotate({angle:.3f} 36 46)"><circle cx="36" cy="46" r="21" fill="url(#pkTop)"/>'
                 f'<rect x="33.5" y="26.5" width="5" height="13" rx="2.5" fill="{ACCENT}"/></g>'
                 '<circle cx="36" cy="46" r="20.4" fill="none" stroke="url(#pkBevel)" stroke-width="1.4"/>')
    s.append("</svg>")
    return "".join(s)


def fader_cap(v):
    top = fader_top(v)
    return f"""<div style="position:absolute;left:273px;top:{top}px;width:46px;height:84px">
<div style="position:absolute;left:2px;top:4px;width:44px;height:82px;border-radius:3px;background:rgba(0,0,0,0.55);filter:blur(5px);transform:translate(6px,5px)"></div>
<div style="position:absolute;left:0;top:0;width:46px;height:84px;clip-path:polygon(0 0,100% 0,99% 20%,96% 35%,93% 50%,96% 65%,99% 80%,100% 100%,0 100%,1% 80%,4% 65%,7% 50%,4% 35%,1% 20%);background:linear-gradient(180deg,#8b8882 0px,#75726d 12px,#3e3c39 12px,#3e3c39 20px,#8f8c86 20px,#8f8c86 21px,#454340 21px,#454340 27px,#8f8c86 27px,#8f8c86 28px,#504e4a 28px,#504e4a 34px,#8f8c86 34px,#8f8c86 35px,#5c5955 35px,#5c5955 40px,{ACCENT} 40px,{ACCENT} 44px,#7c7975 44px,#7c7975 50px,#a3a09a 50px,#a3a09a 51px,#706d68 51px,#706d68 57px,#a3a09a 57px,#a3a09a 58px,#67645f 58px,#67645f 64px,#a3a09a 64px,#a3a09a 65px,#5a5753 65px,#5a5753 71px,#3a3835 71px,#232120 84px)"></div>
<div style="position:absolute;left:3px;top:40px;width:40px;height:4px;box-shadow:0 0 5px rgba(242,162,119,0.7)"></div></div>"""


def fader_static():
    s = [f'<div style="position:absolute;left:270px;top:{WELL_TOP}px;width:52px;height:{WELL_H}px;border-radius:7px;background:linear-gradient(180deg,#b6b3ab,#bfbcb4);box-shadow:inset 0 3px 5px rgba(0,0,0,0.22),inset 0 -1px 0 rgba(255,255,255,0.35),0 1px 0 rgba(255,255,255,0.45)"></div>',
         f'<div style="position:absolute;left:287px;top:{SLOT_TOP}px;width:18px;height:{SLOT_H}px;border-radius:2px;background:linear-gradient(90deg,#0e0e0d,#262523 50%,#121211);box-shadow:inset 0 4px 6px rgba(0,0,0,0.8),0 1px 0 rgba(255,255,255,0.35)"></div>']
    tops = [round(LINE_MIN - n * (LINE_MIN - LINE_MAX) / 10) - 9 for n in range(11)]
    for n, t in enumerate(tops):
        s.append(f'<div style="position:absolute;left:228px;top:{t}px;width:22px;height:18px;text-align:right;font-size:13px;line-height:18px;font-weight:700;color:#f6f4ee;text-shadow:0 1px 1px rgba(0,0,0,0.18)">{n}</div>')
        for x in (254, 328):
            s.append(f'<div style="position:absolute;left:{x}px;top:{t + 8}px;width:12px;height:2px;border-radius:1px;background:#f6f4ee"></div>')
    hatch = "background-image:repeating-linear-gradient(0deg,rgba(246,244,238,0.9) 0 1px,transparent 1px 3px),repeating-linear-gradient(90deg,rgba(246,244,238,0.9) 0 1px,transparent 1px 3px);opacity:0.8"
    for x in (255, 329):
        s.append(f'<div style="position:absolute;left:{x}px;top:{round(LINE_MIN - 0.75 * (LINE_MIN - LINE_MAX)) - 6}px;width:11px;height:13px;{hatch}"></div>')
    s.append(f'<div class="lbl" style="position:absolute;left:246px;top:{FADER_LABEL_TOP}px;width:100px;text-align:center">Master</div>')
    return "".join(s)


CASE_W, CASE_H, CASE_R = 400, 584, 20


def case_svg():
    """Flat top with a soft rounded rim: blurred inset light on the top/left edge
    rolling into shade on the bottom/right. No lines or seams."""
    W, H, R = CASE_W, CASE_H, CASE_R
    return (f'<div style="position:absolute;left:0;top:0;width:{W}px;height:{H}px;border-radius:{R}px;'
            'background:linear-gradient(155deg,#dddad2 0%,#d2cfc7 40%,#c2bfb7 100%);'
            'box-shadow:inset 0 9px 9px -6px rgba(255,255,255,0.85),inset 8px 0 9px -6px rgba(255,255,255,0.5),'
            'inset 0 -11px 11px -6px rgba(70,66,58,0.38),inset -10px 0 11px -6px rgba(70,66,58,0.26),'
            '0 2px 2px rgba(0,0,0,0.3)"></div>')


SCENE_STATIC = """
WOOD
<div style="position:absolute;left:470px;top:70px;width:400px;height:560px;border-radius:26px;background:rgba(0,0,0,0.85);filter:blur(38px);transform:translate(34px,26px) skewX(-6deg)"></div>
<div style="position:absolute;left:446px;top:40px;width:400px;height:580px;border-radius:22px;background:rgba(0,0,0,0.9);filter:blur(10px);transform:translate(8px,8px)"></div>
<div style="position:absolute;left:418px;top:394px;width:28px;height:70px;border-radius:6px;background:linear-gradient(90deg,#0a0a0a,#3e3e3e 40%,#1a1a1a 75%,#0c0c0c);box-shadow:4px 8px 10px rgba(0,0,0,0.7)"><div style="position:absolute;left:4px;top:14px;width:11px;height:42px;border-radius:3px;background:linear-gradient(90deg,#6e6e6e,#f0f0f0 45%,#8a8a8a 70%,#5a5a5a);box-shadow:inset 0 0 0 1px rgba(0,0,0,0.25)"></div></div>
<div style="position:absolute;left:834px;top:192px;width:28px;height:70px;border-radius:6px;background:linear-gradient(270deg,#0a0a0a,#3e3e3e 40%,#1a1a1a 75%,#0c0c0c);box-shadow:8px 10px 12px rgba(0,0,0,0.7)"><div style="position:absolute;right:4px;top:14px;width:11px;height:42px;border-radius:3px;background:linear-gradient(90deg,#5a5a5a,#8a8a8a 30%,#f0f0f0 55%,#6e6e6e);box-shadow:inset 0 0 0 1px rgba(0,0,0,0.25)"></div></div>
<div style="position:absolute;left:834px;top:374px;width:28px;height:70px;border-radius:6px;background:linear-gradient(270deg,#0a0a0a,#3e3e3e 40%,#1a1a1a 75%,#0c0c0c);box-shadow:8px 10px 12px rgba(0,0,0,0.7)"><div style="position:absolute;right:4px;top:14px;width:11px;height:42px;border-radius:3px;background:linear-gradient(90deg,#5a5a5a,#8a8a8a 30%,#f0f0f0 55%,#6e6e6e);box-shadow:inset 0 0 0 1px rgba(0,0,0,0.25)"></div></div>
CABLES
"""

# Wood desk: old walnut. Vertical boards drawn per pixel by a seeded JS
# generator inside the headless render: wavy "cathedral" figure lines, broad
# tone bands, fine pore dashes along the grain and a few pale flecks. Then an
# overhead lamp and a vignette so the pedal stays the focus.
BOARD_W = 320

WOOD_JS = r"""
(function(){
const W=1280,H=628,BW=%(bw)d;
const c=document.getElementById('woodcv'),g=c.getContext('2d'),im=g.createImageData(W,H),d=im.data;
function rng(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;}}
function makeNoise(seed){const r=rng(seed),N=256,p=new Float32Array(N*N);for(let i=0;i<N*N;i++)p[i]=r();
 return function(x,y){let xi=Math.floor(x),yi=Math.floor(y),xf=x-xi,yf=y-yi;xi&=255;yi&=255;const x1=(xi+1)&255,y1=(yi+1)&255;
  const u=xf*xf*(3-2*xf),v=yf*yf*(3-2*yf);const a=p[yi*N+xi],b=p[yi*N+x1],cc=p[y1*N+xi],dd=p[y1*N+x1];
  return a+(b-a)*u+(cc-a)*v+(a-b-cc+dd)*u*v;};}
function fbm(n,x,y,o){let s=0,amp=0.5,f=1;for(let i=0;i<o;i++){s+=amp*n(x*f,y*f);f*=2.03;amp*=0.5;}return s/(1-Math.pow(0.5,o));}
const boards=[];for(let b=0;b<Math.ceil(W/BW);b++){boards.push({n1:makeNoise(101+b*17),n2:makeNoise(211+b*13),n3:makeNoise(307+b*29),n4:makeNoise(401+b*7),
 tone:[0.02,-0.07,0.05,-0.03][b%%4],cx:BW*(0.3+0.4*rng(9+b)()),ph:rng(77+b)()*6.28});}
const DARK=[36,20,14],MID=[88,50,34],LIGHT=[134,86,60];
for(let y=0;y<H;y++){for(let x=0;x<W;x++){
 const b=Math.min(boards.length-1,Math.floor(x/BW)),B=boards[b],bx=x-b*BW;
 // figure: distance from a wandering centre line, bent into arches
 const warp=(fbm(B.n1,bx*0.006,y*0.0022,4)-0.5)*90+Math.sin(y*0.0045+B.ph)*22;
 const dx=bx-B.cx+warp;
 const arch=Math.sqrt(dx*dx+Math.pow(Math.max(0,(y-300-B.cx*0.4))*0.18,2));
 const ring=arch/11+fbm(B.n2,bx*0.02,y*0.004,3)*2.2;
 const fr=ring-Math.floor(ring);
 const line=Math.pow(Math.max(0,1-Math.abs(fr-0.5)*2.0),2)*(0.5+fbm(B.n4,bx*0.03,y*0.01,2));          // dark figure lines
 const band=fbm(B.n3,bx*0.008,y*0.0016,4)-0.5;                      // broad tone bands
 const pore=B.n4(x*1.5,y*0.08+bx*0.003)*0.7+B.n1(x*2.7+90,y*0.12)*0.3;                            // fine pores, long along y
 const fleck=B.n2(x*1.3+50,y*0.11);
 let t=0.50+band*0.75+B.tone-line*0.16;
 if(pore>0.66)t-=(pore-0.66)*1.5;
 if(fleck>0.95)t+=(fleck-0.95)*2.0;
 t=Math.max(0,Math.min(1,t));
 let r,gg,bb;if(t<0.5){const k=t/0.5;r=DARK[0]+(MID[0]-DARK[0])*k;gg=DARK[1]+(MID[1]-DARK[1])*k;bb=DARK[2]+(MID[2]-DARK[2])*k;}
 else{const k=(t-0.5)/0.5;r=MID[0]+(LIGHT[0]-MID[0])*k;gg=MID[1]+(LIGHT[1]-MID[1])*k;bb=MID[2]+(LIGHT[2]-MID[2])*k;}
 if(bx<1){r*=0.7;gg*=0.7;bb*=0.7;}
 const o=(y*W+x)*4;d[o]=r;d[o+1]=gg;d[o+2]=bb;d[o+3]=255;}}
g.putImageData(im,0,0);
})();
"""


def wood():
    return ('<canvas id="woodcv" width="1280" height="628" style="position:absolute;left:0;top:0"></canvas>'
            '<script>' + (WOOD_JS % {"bw": BOARD_W}) + '</script>'
            '<svg width="1280" height="628" style="position:absolute;left:0;top:0"><defs>'
            '<radialGradient id="lamp" cx="0.5" cy="0.42" r="0.75"><stop offset="0" stop-color="#ffe9cc" stop-opacity="0.14"/>'
            '<stop offset="0.5" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.6"/></radialGradient>'
            '</defs><rect width="1280" height="628" fill="url(#lamp)"/></svg>')


PLUG = """<g transform="translate({tx} {ty}) scale({sx} 1.5)"><rect x="-184" y="-9" width="54" height="18" rx="5" fill="url(#spring)"/><rect x="-184" y="-9" width="54" height="18" rx="5" fill="url(#springShade)"/><path d="M-118 -15 L-134 -11 L-134 11 L-118 15 Z" fill="url(#chromeDark)"/><rect x="-120" y="-15" width="110" height="30" rx="4" fill="url(#chrome)"/><rect x="-92" y="-15" width="38" height="30" fill="url(#knurl)"/><rect x="-98" y="-15" width="3" height="30" fill="#000" opacity="0.35"/><rect x="-52" y="-15" width="3" height="30" fill="#000" opacity="0.35"/><rect x="-116" y="-10" width="20" height="3" rx="1.5" fill="#fff" opacity="0.18"/><rect x="-48" y="-10" width="36" height="3" rx="1.5" fill="#fff" opacity="0.18"/><rect x="-12" y="-17" width="12" height="34" rx="2" fill="url(#chromeDark)"/><rect x="-12" y="-17" width="2" height="34" fill="#000" opacity="0.3"/></g>"""

CABLES = """<svg width="1280" height="628" style="position:absolute;left:0;top:0;overflow:visible"><defs>
<filter id="cableShadow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="7"/></filter>
<linearGradient id="chrome" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#151515"/><stop offset="0.2" stop-color="#4a4a4a"/><stop offset="0.45" stop-color="#202020"/><stop offset="0.75" stop-color="#0c0c0c"/><stop offset="0.9" stop-color="#262626"/><stop offset="1" stop-color="#050505"/></linearGradient>
<linearGradient id="chromeDark" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0a0a0a"/><stop offset="0.25" stop-color="#383838"/><stop offset="0.6" stop-color="#121212"/><stop offset="1" stop-color="#000000"/></linearGradient>
<linearGradient id="springShade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity="0.5"/><stop offset="0.3" stop-color="#fff" stop-opacity="0.25"/><stop offset="0.6" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.7"/></linearGradient>
<pattern id="knurl" patternUnits="userSpaceOnUse" width="4" height="30"><rect x="0" y="0" width="1.5" height="30" fill="#000" opacity="0.35"/><rect x="2" y="0" width="1" height="30" fill="#fff" opacity="0.08"/></pattern>
<pattern id="spring" patternUnits="userSpaceOnUse" width="4" height="18"><rect x="0" y="0" width="4" height="18" fill="#0a0a0a"/><rect x="0.5" y="0" width="2.5" height="18" fill="#3c3c3c"/></pattern>
</defs>
<g filter="url(#cableShadow)" opacity="0.85" transform="translate(12 16)"><path d="M188 429 C 96 429 86 566 14 664" fill="none" stroke="#000" stroke-width="28"/><path d="M1092 227 C 1176 227 1196 116 1330 56" fill="none" stroke="#000" stroke-width="28"/><path d="M1092 409 C 1184 409 1204 546 1330 626" fill="none" stroke="#000" stroke-width="28"/><rect x="188" y="404" width="230" height="50" rx="6" fill="#000"/><rect x="862" y="202" width="230" height="50" rx="6" fill="#000"/><rect x="862" y="384" width="230" height="50" rx="6" fill="#000"/></g>
<g fill="none" stroke-linecap="round"><path d="M188 429 C 96 429 86 566 14 664" stroke="#111111" stroke-width="26"/><path d="M188 422 C 98 422 80 556 8 654" stroke="#5a5a5a" stroke-width="4" opacity="0.6"/><path d="M1092 227 C 1176 227 1196 116 1330 56" stroke="#111111" stroke-width="26"/><path d="M1092 220 C 1172 220 1190 108 1330 48" stroke="#5a5a5a" stroke-width="4" opacity="0.6"/><path d="M1092 409 C 1184 409 1204 546 1330 626" stroke="#111111" stroke-width="26"/><path d="M1092 402 C 1188 402 1212 536 1330 616" stroke="#5a5a5a" stroke-width="4" opacity="0.6"/></g>
""" + PLUG.format(tx=418, ty=429, sx=1.25) + PLUG.format(tx=862, ty=227, sx=-1.25) + PLUG.format(tx=862, ty=409, sx=-1.25) + "</svg>"


def tab(show, knob_v=0.5, fader_v=0.7, on=True, knob_only=None):
    """Full tab-area markup. `show`: set of layers. knob_only: index of the one knob to draw."""
    st = "static" in show
    s = ['<div class="tab">']
    if st:
        s.append(SCENE_STATIC.replace("WOOD", wood()).replace("CABLES", CABLES))
    # Case: flat top with a soft rounded rim (see case_svg).
    s.append(f'<div style="position:absolute;left:{FACE[0]}px;top:{FACE[1]}px;width:400px;height:584px">')
    if st:
        s.append(case_svg())
    if st:
        s.append(f'<div style="position:absolute;left:26px;top:20px;font-family:Orbitron,sans-serif;font-weight:900;font-size:22px;line-height:26px;letter-spacing:0.02em;color:{ACCENT};text-shadow:0 1px 0 rgba(0,0,0,0.12)">{WORDMARK}</div>')
    panel_bg = ("background:linear-gradient(180deg,#c7c4bc 0%,#cbc8c0 8%,#c9c6be 100%);box-shadow:inset 0 3px 6px rgba(0,0,0,0.13),inset 0 1px 0 rgba(0,0,0,0.06),0 1px 0 rgba(255,255,255,0.5),0 -1px 0 rgba(0,0,0,0.05);") if st else ""
    s.append(f'<div style="position:absolute;left:22px;top:62px;width:356px;height:{PANEL_H}px;border-radius:12px;{panel_bg}">')
    for i, (label, _, x, y) in enumerate(KNOBS):
        if knob_only is not None and i != knob_only:
            continue
        s.append(f'<div style="position:absolute;left:{x}px;top:{y}px;width:100px;height:110px">')
        s.append(f'<div style="position:absolute;left:14px;top:0;width:72px;height:84px">')
        s.append(knob_svg(-135 + knob_v * 270, st, "knob" in show))
        s.append("</div>")
        if st:
            s.append(f'<div class="lbl" style="position:absolute;left:0;top:88px;width:100px;text-align:center">{label}</div>')
        s.append("</div>")
    s.append(f'<div style="position:absolute;left:{FADER_DX}px;top:{FADER_DY}px;width:356px;height:{PANEL_H}px">')
    if st:
        s.append(fader_static())
    if "fader" in show:
        s.append(fader_cap(fader_v))
    s.append("</div>")
    s.append("</div>")  # panel
    s.append("</div></div>")  # face, tab
    return "".join(s)


def cam(box, inner):
    x, y, w, h = box
    return f'<div class="cam" style="width:{w}px;height:{h}px"><div style="position:absolute;left:{-x}px;top:{-y}px">{inner}</div></div>'


def shoot(html, w, h, out, tmp):
    page = os.path.join(tmp, "page.html")
    with open(page, "w") as f:
        f.write(HEAD + html + "</body></html>")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1", "--default-background-color=00000000",
                    "--virtual-time-budget=6000", f"--window-size={w},{h}",
                    f"--screenshot={out}", "file://" + page],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    img = Image.open(out).convert("RGBA")
    if img.size != (w, h):
        img = img.crop((0, 0, w, h))
    return img


def strip(frames_html, w, h, out, tmp, chunk=40):
    parts = []
    for c in range(0, len(frames_html), chunk):
        part = frames_html[c:c + chunk]
        parts.append(shoot("".join(part), w, h * len(part), os.path.join(tmp, f"chunk{c}.png"), tmp))
    full = Image.new("RGBA", (w, h * len(frames_html)))
    for c, p in enumerate(parts):
        full.paste(p, (0, c * chunk * h))
    full.save(out, optimize=True)
    print(f"  {os.path.basename(out)}  {w}x{h} x {len(frames_html)}")


def render_art(tmp):
    os.makedirs(OUT, exist_ok=True)
    bg = shoot(tab({"static"}), 1280, 628, os.path.join(tmp, "bg.png"), tmp)
    bg.convert("RGB").save(os.path.join(OUT, "bg.png"), optimize=True)
    print("  bg.png  1280x628")

    kx, ky = knob_pos(KNOBS[0])
    box = (kx, ky, KNOB_W, KNOB_H)
    frames = [cam(box, tab({"knob"}, knob_v=f / (KNOB_FRAMES - 1), knob_only=0)) for f in range(KNOB_FRAMES)]
    strip(frames, KNOB_W, KNOB_H, os.path.join(OUT, "knob.png"), tmp)

    frames = [cam(FADER_BOX, tab({"fader"}, fader_v=f / (FADER_FRAMES - 1), knob_only=-1)) for f in range(FADER_FRAMES)]
    strip(frames, FADER_BOX[2], FADER_BOX[3], os.path.join(OUT, "fader.png"), tmp)




# ---------------------------------------------------------------------------
# TUI.json / Q-Links.json. Written as text: overlay widgets need duplicate
# "version" keys, which a JSON library cannot produce.
# ---------------------------------------------------------------------------
class Dup(list):
    """Ordered key/value pairs that may repeat keys."""


def dump(v, ind=0):
    sp = "    " * ind
    sp1 = "    " * (ind + 1)
    if isinstance(v, Dup):
        if not v:
            return "{}"
        return "{\n" + ",\n".join(f'{sp1}"{k}": {dump(x, ind + 1)}' for k, x in v) + "\n" + sp + "}"
    if isinstance(v, dict):
        return dump(Dup(v.items()), ind)
    if isinstance(v, list):
        if not v:
            return "[]"
        return "[\n" + ",\n".join(sp1 + dump(x, ind + 1) for x in v) + "\n" + sp + "]"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return str(v)


TRANSPARENT = {"version": 1, "focussed": {"version": 1, "colour": "0", "image": ""},
               "unfocussed": {"version": 1, "colour": "0", "image": ""}}


def bounds(rect, focus="No"):
    return {"version": 1, "acceptsHWFocus": focus, "showWhenDataModelInvalid": "Hide",
            "whenVisible": "Always", "boundsType": "Absolute", "bounds": rect}


def entry(name, typ, data, rect, remap=None, focus="No"):
    return {"version": 2,
            "componentData": {"version": 1, "name": name, "type": typ, "data": data},
            "handle remapping": {"version": 1, "map": [{"key": "Data", "value": remap}] if remap else []},
            "bounds": bounds(rect, focus)}


def component(actions, children, ignore=False):
    return {"version": 2, "actions": actions, "backgroundData": TRANSPARENT,
            "ignoreMousePresses": ignore, "disableCoarseDataWheel": False, "componentsData": children}


def action(on, handler, extra=""):
    return {"version": 1, "onAction": on, "handler": handler, "handleName": "Data", "additionalData": extra}


EDIT_ACTIONS = [action("Mouse Down", "Q-Link"), action("Double Click", "Show Overlay", "knob overlay"),
                action("Enter Pressed", "Show Overlay", "knob overlay")]


def overlay_def(name, polarity):
    data = Dup([("version", 2), ("version", 1),
                ("actions", [{"version": 1, "onAction": "Focus Lost", "handler": "Focus Lost", "handleName": "Focus Lost", "additionalData": ""}]),
                ("overlayType", "Knob With Header"), ("scaleType", "Linear"),
                ("polarityType", polarity), ("showMinusSign", True), ("handleName", "Data")])
    child = {"version": 2,
             "componentData": {"version": 1, "name": "overlay", "type": "KnobOverlay", "data": data},
             "handle remapping": {"version": 1, "map": []},
             "bounds": {"version": 1, "acceptsHWFocus": "Yes", "showWhenDataModelInvalid": "Show",
                        "whenVisible": "Always", "boundsType": "Absolute", "bounds": "0 0 1280 800"}}
    return {"key": name, "value": component([], [child], ignore=True)}


def write_skin():
    def r(x, y, w, h):
        return f"{x} {y} {w} {h}"

    knob_data = {"version": 3, "knobType": "FilmStrip", "filmStrip": "knob.png", "numFrames": KNOB_FRAMES,
                 "invert": False, "dragOrientation": "Vertical", "handleName": "Data"}
    fader_data = {"version": 3, "knobType": "FilmStrip", "filmStrip": "fader.png", "numFrames": FADER_FRAMES,
                  "invert": False, "dragOrientation": "Vertical", "handleName": "Data"}
    # Bipolar controls use the bipolar overlay.
    bip = {P_HIGH, P_LOW}

    defs = [
        {"key": "pkKnob", "value": component(EDIT_ACTIONS, [entry("knob", "Knob", knob_data, r(0, 0, KNOB_W, KNOB_H))])},
        {"key": "pkKnobBi", "value": component(
            [action("Mouse Down", "Q-Link"), action("Double Click", "Show Overlay", "knob overlay bi"),
             action("Enter Pressed", "Show Overlay", "knob overlay bi")],
            [entry("knob", "Knob", knob_data, r(0, 0, KNOB_W, KNOB_H))])},
        {"key": "pkFader", "value": component(EDIT_ACTIONS, [entry("fader", "Knob", fader_data, r(0, 0, FADER_BOX[2], FADER_BOX[3]))])},
        overlay_def("knob overlay", "Unipolar"),
        overlay_def("knob overlay bi", "Bipolar"),
    ]

    kids = [entry("bg", "Image", {"version": 2, "imageType": "Regular", "colour": "0", "image": "bg.png"}, r(0, 0, 1280, 628))]
    for k in KNOBS:
        label, p = k[0], k[1]
        x, y = knob_pos(k)
        kids.append(entry(label, "pkKnobBi" if p in bip else "pkKnob", {"version": 1, "handleName": "Data"},
                          r(x, y, KNOB_W, KNOB_H), f"Parameter {p}", "Yes"))
    kids.append(entry("Master", "pkFader", {"version": 1, "handleName": "Data"}, r(*FADER_BOX), f"Parameter {P_MASTER}", "Yes"))

    root = {"version": 2, "actions": [],
            "backgroundData": {"version": 1, "focussed": {"version": 1, "colour": "ff161616", "image": ""},
                               "unfocussed": {"version": 1, "colour": "ff161616", "image": ""}},
            "ignoreMousePresses": False, "disableCoarseDataWheel": False, "componentsData": kids}
    tabd = Dup([("version", 1), ("tabName", "Main"), ("fnKeyIndex", 0), ("fnKeySubIndex", 0),
                ("componentDefinition", root), ("qlinkBoundsData", [])])
    tui = {"pageData": Dup([
        ("version", 1),
        ("componentDefinitions", {"version": 2, "importFiles": [], "localComponentDefinitions": defs}),
        ("replacementStrings", []),
        ("info", {"version": 1, "type": "CompleteDescription"}),
        ("tabs", [tabd]),
    ])}
    with open(os.path.join(OUT, "TUI.json"), "w") as f:
        f.write(dump(tui) + "\n")

    # Q-Links, column-major from the top-left (13, 9, 5, 1 is the first column):
    #   column 1: Trim, High, Low, Channel      column 2: Master
    order = [P_TRIM, P_HIGH, P_LOW, P_CHANNEL, P_MASTER]
    slots = [13, 9, 5, 1, 14, 10, 6, 2, 15, 11, 7, 3, 16, 12, 8, 4]
    q = {f"Q-Link {n}": -1 for n in range(1, 17)}
    for slot, p in zip(slots, order):
        q[f"Q-Link {slot}"] = p
    q = {f"Q-Link {n}": q[f"Q-Link {n}"] for n in range(1, 17)}
    prog = {f"Q-Link {n}": (order[n - 1] if n <= len(order) else -1) for n in range(1, 17)}
    ql = Dup([("version", 4), ("info", {"version": 1, "type": "CompleteDescription"}),
              ("Screen Mode Q-Links", {"version": 4, "map": [
                  Dup([("Tab", 1), ("SubTab", 1), ("Bank Direction", "Column"), ("Q-Links", q)])]}),
              ("Program Mode Q-Links", prog)])
    with open(os.path.join(OUT, "Q-Links.json"), "w") as f:
        f.write(dump(ql) + "\n")
    print("  TUI.json, Q-Links.json")


def make_preview():
    """Composite the default state using the bounds read back from TUI.json,
    so the preview shows exactly where the MPC will draw each control."""
    import re
    tui = open(os.path.join(OUT, "TUI.json")).read()
    defaults = {"pkKnob": None, "pkKnobBi": 0.5}
    norm = {P_TRIM: 1 / 3, P_HIGH: 0.5, P_LOW: 0.5, P_CHANNEL: 0.75, P_MASTER: 0.75}
    prev = Image.open(os.path.join(OUT, "bg.png")).convert("RGBA")
    pat = re.compile(r'"type": "(pkKnob|pkKnobBi|pkFader)"[\s\S]*?"value": "Parameter (\d+)"[\s\S]*?"bounds": "([\d. ]+)"')
    found = 0
    for typ, param, rect in pat.findall(tui):
        x, y, w, h = [int(float(v)) for v in rect.split()]
        img = Image.open(os.path.join(OUT, "fader.png" if typ == "pkFader" else "knob.png"))
        frames = FADER_FRAMES if typ == "pkFader" else KNOB_FRAMES
        fh = img.height // frames
        fr = round(norm[int(param)] * (frames - 1))
        prev.alpha_composite(img.crop((0, fr * fh, img.width, (fr + 1) * fh)), (x, y))
        found += 1
    prev.convert("RGB").save(os.path.join(HERE, "preview.png"))
    print(f"  art/preview.png  ({found} controls placed from TUI.json)")


def main():
    if not os.path.exists(CHROME):
        sys.exit("Google Chrome not found at " + CHROME)
    tmp = tempfile.mkdtemp(prefix="424skin-")
    try:
        if "--json-only" not in sys.argv:
            render_art(tmp)
        write_skin()
        make_preview()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
