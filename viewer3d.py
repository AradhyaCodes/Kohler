"""Interactive 3D view (three.js from cdnjs) built from the same layout coordinates. Drag = rotate, wheel = zoom."""
import json
from typing import List, Optional

from spatial_optimizer import DOOR_WIDTH, WINDOW_WIDTH, clamp_offset

HEIGHTS = {"toilet": 1.4, "smart toilet": 1.4, "vanity": 2.8, "basin": 0.5, "sink": 0.5,
           "shower": 7.0, "shower enclosure": 7.0, "bathtub": 1.8}
COLORS = {"toilet": 0xffc107, "smart toilet": 0xffc107, "vanity": 0x0d6efd, "basin": 0x0d6efd, "sink": 0x0d6efd,
          "shower": 0x20c997, "shower enclosure": 0x20c997, "bathtub": 0x6f42c1}

_TEMPLATE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>html,body{margin:0;background:#f1f3f5;font-family:Arial,sans-serif}
#c{width:100%;height:500px;cursor:grab;touch-action:none}#hint{position:absolute;left:10px;top:8px;font-size:12px;color:#495057}
#err{padding:20px;color:#c92a2a;display:none}</style></head><body>
<div id="hint">Drag to rotate - scroll to zoom</div><div id="c"></div><div id="err">3D view needs WebGL and internet access to load three.js.</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const D = __DATA__;
try {
const box = document.getElementById('c');
const W = D.W, L = D.L;
const renderer = new THREE.WebGLRenderer({antialias:true}); renderer.setPixelRatio(window.devicePixelRatio||1);
box.appendChild(renderer.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color(0xf1f3f5);
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 500);
scene.add(new THREE.AmbientLight(0xffffff, 0.75));
const sun = new THREE.DirectionalLight(0xffffff, 0.6); sun.position.set(W, 20, -L); scene.add(sun);

function add(x1, z1, w, d, h, color, opacity, elev) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d),
    new THREE.MeshLambertMaterial({color: color, transparent: opacity < 1, opacity: opacity}));
  m.position.set(x1 + w/2, (elev||0) + h/2, z1 + d/2); scene.add(m);
  const e = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry), new THREE.LineBasicMaterial({color: 0x212529}));
  e.position.copy(m.position); scene.add(e); return m;
}
function opening(wall, off, width, depth) {
  if (wall === 'North') return [off, 0, width, depth];
  if (wall === 'South') return [off, L - depth, width, depth];
  if (wall === 'West') return [0, off, depth, width];
  return [W - depth, off, depth, width];
}
add(0, 0, W, L, 0.1, 0xe9ecef, 1, -0.1);                       // floor
const t = 0.2, wh = 8;                                          // walls (translucent)
add(0, -t, W, t, wh, 0x868e96, 0.12); add(0, L, W, t, wh, 0x868e96, 0.12);
add(-t, 0, t, L, wh, 0x868e96, 0.12); add(W, 0, t, L, wh, 0x868e96, 0.12);
if (D.wet) { const o = opening(D.wet, 0, (D.wet==='North'||D.wet==='South')?W:L, 0.35);
  add(o[0], o[1], o[2], o[3], 0.05, 0x0d6efd, 0.6, 0); }
if (D.door) { const o = opening(D.door.wall, D.door.offset, D.door.width, 0.25); add(o[0], o[1], o[2], o[3], 6.8, 0x8d6e63, 0.85); }
if (D.window) { const o = opening(D.window.wall, D.window.offset, D.window.width, 0.25); add(o[0], o[1], o[2], o[3], 3, 0x74c0fc, 0.7, 3); }
D.items.forEach(it => {
  const c = it.clear; add(c[0], c[1], c[2]-c[0], c[3]-c[1], 0.03, it.color, 0.25, 0);   // clearance zone
  add(it.x, it.y, it.w, it.h, it.height, it.color, it.height > 5 ? 0.45 : 1, 0);
});

let yaw = 0.6, pitch = 0.65, radius = Math.max(W, L) * 1.7, drag = null;
function draw() {
  const w = box.clientWidth, h = box.clientHeight; renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix();
  camera.position.set(W/2 + radius*Math.sin(yaw)*Math.cos(pitch), radius*Math.sin(pitch), L/2 + radius*Math.cos(yaw)*Math.cos(pitch));
  camera.lookAt(W/2, 1.5, L/2); renderer.render(scene, camera);
}
const el = renderer.domElement;
el.addEventListener('pointerdown', e => { drag = [e.clientX, e.clientY]; el.setPointerCapture(e.pointerId); });
el.addEventListener('pointerup', () => drag = null);
el.addEventListener('pointermove', e => { if (!drag) return;
  yaw -= (e.clientX - drag[0]) * 0.01; pitch = Math.min(1.5, Math.max(0.1, pitch + (e.clientY - drag[1]) * 0.01));
  drag = [e.clientX, e.clientY]; draw(); });
el.addEventListener('wheel', e => { e.preventDefault(); radius = Math.min(80, Math.max(4, radius * (1 + e.deltaY * 0.001))); draw(); }, {passive:false});
window.addEventListener('resize', draw); draw();
} catch (err) { document.getElementById('c').style.display='none'; document.getElementById('err').style.display='block'; }
</script></body></html>"""


def build_3d_html(layout: List[dict], room_w: float, room_l: float, door: Optional[tuple],
                  window: Optional[tuple], wet_wall: Optional[str]) -> str:
    items = []
    for it in layout:
        cat = it["category"].lower()
        items.append({"x": it["x"], "y": it["y"], "w": it["w"], "h": it["h"], "clear": it["clear"],
                      "color": COLORS.get(cat, 0x6c757d), "height": HEIGHTS.get(cat, 2.0)})
    data = {"W": room_w, "L": room_l, "wet": wet_wall, "items": items, "door": None, "window": None}
    if door:
        wid = door[2] if len(door) > 2 else DOOR_WIDTH
        data["door"] = {"wall": door[0], "offset": clamp_offset(door[1], door[0], wid, room_w, room_l), "width": wid}
    if window:
        data["window"] = {"wall": window[0], "offset": clamp_offset(window[1], window[0], WINDOW_WIDTH, room_w, room_l),
                          "width": WINDOW_WIDTH}
    return _TEMPLATE.replace("__DATA__", json.dumps(data))
