import socket
import json
import ctypes
from ctypes import wintypes
from aiohttp import web
from pynput.mouse import Controller as MouseController, Button
from pynput.keyboard import Controller as KeyController, Key

mouse = MouseController()
keyboard = KeyController()
user32 = ctypes.windll.user32

# ==========================================================
# Windows Native DirectManipulation Touch Injection Engine
# ==========================================================
class POINTER_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerType", wintypes.DWORD),
        ("pointerId", ctypes.c_uint32),
        ("frameId", ctypes.c_uint32),
        ("pointerFlags", wintypes.DWORD),
        ("sourceDevice", wintypes.HANDLE),
        ("hwndTarget", wintypes.HWND),
        ("ptPixelLocation", wintypes.POINT),
        ("ptHimetricLocation", wintypes.POINT),
        ("ptPixelLocationRaw", wintypes.POINT),
        ("ptHimetricLocationRaw", wintypes.POINT),
        ("dwTime", wintypes.DWORD),
        ("historyCount", ctypes.c_uint32),
        ("InputData", ctypes.c_int32),
        ("dwKeyStates", wintypes.DWORD),
        ("PerformanceCount", ctypes.c_uint64),
        ("ButtonChangeType", ctypes.c_int32)
    ]

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG)
    ]

class POINTER_TOUCH_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerInfo", POINTER_INFO),
        ("touchFlags", ctypes.c_uint32),
        ("touchMask", ctypes.c_uint32),
        ("rcContact", RECT),
        ("rcContactRaw", RECT),
        ("orientation", ctypes.c_uint32),
        ("pressure", ctypes.c_uint32)
    ]

class PrecisionZoomEngine:
    def __init__(self):
        self.available = False
        try:
            if user32.InitializeTouchInjection(2, 1):
                self.available = True
        except Exception:
            self.available = False
        self.active = False
        self.center_x = 0
        self.center_y = 0
        self.current_span = 280

    def start_pinch(self):
        if not self.available:
            return
        cx, cy = mouse.position
        self.center_x, self.center_y = int(cx), int(cy)
        self.current_span = 280
        self.active = True
        self._inject_frame(self.current_span, 0x00010000 | 0x00000002 | 0x00000004) # DOWN | INRANGE | INCONTACT

    def update_delta(self, delta_px):
        if not self.available or not self.active:
            return
        self.current_span = max(25, min(950, self.current_span + int(delta_px * 2.2)))
        self._inject_frame(self.current_span, 0x00020000 | 0x00000002 | 0x00000004) # UPDATE | INRANGE | INCONTACT

    def end_pinch(self):
        if not self.available or not self.active:
            return
        self._inject_frame(self.current_span, 0x00040000) # UP
        self.active = False
        # Instantly unhide and restore hardware mouse cursor at the focal point
        user32.mouse_event(0x0001, 1, 1, 0, 0)
        user32.mouse_event(0x0001, -1, -1, 0, 0)

    def _inject_frame(self, span, flags):
        contacts = (POINTER_TOUCH_INFO * 2)()
        for i, offset in enumerate([-span, span]):
            contacts[i].pointerInfo.pointerType = 2 # PT_TOUCH
            contacts[i].pointerInfo.pointerId = i
            contacts[i].pointerInfo.pointerFlags = flags
            contacts[i].pointerInfo.ptPixelLocation.x = max(0, self.center_x + offset)
            contacts[i].pointerInfo.ptPixelLocation.y = max(0, self.center_y)
            contacts[i].touchFlags = 0
            contacts[i].touchMask = 0x00000004 # PRESSURE
            contacts[i].pressure = 32000
        user32.InjectTouchInput(2, contacts)

zoom_engine = PrecisionZoomEngine()

# ==========================================================
# Fullscreen Web Client with Working UI Drawer & Controls
# ==========================================================
HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <title>AirTrack</title>
  <style>
    * { box-sizing: border-box; -webkit-touch-callout: none; user-select: none; }
    body, html {
      margin: 0; padding: 0; width: 100vw; height: 100vh; overflow: hidden;
      background: #0d0d0f; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    #pad { position: absolute; inset: 0; width: 100%; height: 100%; z-index: 1; touch-action: none; }
    
    #status-badge {
      position: absolute; top: calc(env(safe-area-inset-top, 12px) + 8px); left: 16px;
      display: flex; align-items: center; gap: 6px;
      padding: 5px 10px; border-radius: 12px;
      background: rgba(255,255,255,0.08); backdrop-filter: blur(10px);
      font-size: 11px; font-weight: 500; color: #8e8e93;
      pointer-events: none; z-index: 5;
    }
    #status-dot { width: 6px; height: 6px; border-radius: 50%; background: #ff453a; }

    #gear-btn {
      position: absolute; top: calc(env(safe-area-inset-top, 12px) + 6px); right: 16px;
      width: 36px; height: 36px; border-radius: 50%;
      background: rgba(255,255,255,0.1); backdrop-filter: blur(10px);
      border: 1px solid rgba(255,255,255,0.15); color: #fff;
      display: flex; align-items: center; justify-content: center;
      font-size: 18px; z-index: 10; cursor: pointer;
    }

    #drawer {
      display: none; position: absolute; inset: 0; background: rgba(18,18,22,0.92);
      backdrop-filter: blur(25px); -webkit-backdrop-filter: blur(25px);
      z-index: 20; padding: 50px 24px 30px; color: #fff; touch-action: auto;
    }
    .drawer-title { font-size: 18px; font-weight: 600; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; }
    .close-btn { background: #007aff; border: none; color: #fff; padding: 8px 16px; border-radius: 14px; font-size: 13px; font-weight: 600; cursor: pointer; }
    .row { display: flex; justify-content: space-between; align-items: center; margin: 24px 0; font-size: 14px; color: #aeaeb2; }
    input[type=range] { width: 50%; height: 6px; accent-color: #007aff; cursor: pointer; touch-action: auto; }

    #haptic-host { position: fixed; top: -100px; left: -100px; opacity: 0; pointer-events: none; }
  </style>
</head>
<body>
  <div id="haptic-host">
    <label id="haptic-label" for="haptic-toggle">
      <input type="checkbox" switch id="haptic-toggle">
    </label>
  </div>

  <div id="status-badge">
    <div id="status-dot"></div>
    <span id="status-text">Connecting</span>
  </div>

  <button id="gear-btn" aria-label="Settings">⚙</button>

  <div id="drawer">
    <div class="drawer-title">
      <span>Trackpad Settings</span>
      <button class="close-btn" id="close-drawer-btn">Done</button>
    </div>
    <div class="row">
      <span>Pointer Sensitivity: <b id="sens-val">1.8x</b></span>
      <input type="range" id="sens" min="0.8" max="4.0" step="0.1" value="1.8">
    </div>
    <div class="row">
      <span>Scroll Speed: <b id="scroll-val">1.0x</b></span>
      <input type="range" id="scroll" min="0.4" max="2.5" step="0.1" value="1.0">
    </div>
    <div class="row">
      <span>3D Touch Click Force: <b id="force-val">0.45</b></span>
      <input type="range" id="force" min="0.2" max="0.85" step="0.05" value="0.45">
    </div>
  </div>

  <div id="pad"></div>

  <script>
    // Audio Context Acoustic Trackpad Impulses
    let audioCtx = null;
    function playTrackpadImpulse(down = true) {
      try {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === 'suspended') audioCtx.resume();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.frequency.setValueAtTime(down ? 115 : 175, audioCtx.currentTime);
        gain.gain.setValueAtTime(0.35, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + (down ? 0.012 : 0.008));
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + (down ? 0.012 : 0.008));
      } catch (e) {}
    }

    const hapticLabel = document.getElementById('haptic-label');
    function triggerHapticFeedback(down = true) {
      playTrackpadImpulse(down);
      if (navigator.vibrate) navigator.vibrate(down ? 22 : 12);
      try { if (hapticLabel) hapticLabel.click(); } catch(e) {}
    }

    // Config & Persistence
    let sens = parseFloat(localStorage.getItem('tp_sens') || '1.8');
    let scrollSpeed = parseFloat(localStorage.getItem('tp_scroll') || '1.0');
    let forceThreshold = parseFloat(localStorage.getItem('tp_force') || '0.45');

    const sensSlider = document.getElementById('sens');
    const scrollSlider = document.getElementById('scroll');
    const forceSlider = document.getElementById('force');
    const sensVal = document.getElementById('sens-val');
    const scrollVal = document.getElementById('scroll-val');
    const forceVal = document.getElementById('force-val');
    const drawer = document.getElementById('drawer');

    sensSlider.value = sens; sensVal.innerText = sens.toFixed(1) + 'x';
    scrollSlider.value = scrollSpeed; scrollVal.innerText = scrollSpeed.toFixed(1) + 'x';
    forceSlider.value = forceThreshold; forceVal.innerText = forceThreshold.toFixed(2);

    sensSlider.oninput = (e) => {
      sens = parseFloat(e.target.value);
      sensVal.innerText = sens.toFixed(1) + 'x';
      localStorage.setItem('tp_sens', sens);
    };
    scrollSlider.oninput = (e) => {
      scrollSpeed = parseFloat(e.target.value);
      scrollVal.innerText = scrollSpeed.toFixed(1) + 'x';
      localStorage.setItem('tp_scroll', scrollSpeed);
    };
    forceSlider.oninput = (e) => {
      forceThreshold = parseFloat(e.target.value);
      forceVal.innerText = forceThreshold.toFixed(2);
      localStorage.setItem('tp_force', forceThreshold);
    };

    document.getElementById('gear-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      drawer.style.display = 'block';
    });
    document.getElementById('close-drawer-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      drawer.style.display = 'none';
    });

    // WebSocket Management
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    let ws;

    function initSocket() {
      const protocol = location.protocol === 'https:' ? 'wss://' : 'ws://';
      ws = new WebSocket(protocol + location.host + '/ws');
      ws.onopen = () => { statusDot.style.background = '#30d158'; statusText.innerText = 'Ready'; };
      ws.onclose = () => { statusDot.style.background = '#ff453a'; statusText.innerText = 'Offline'; setTimeout(initSocket, 1000); };
    }
    initSocket();

    // Trackpad Surface Handlers
    const pad = document.getElementById('pad');
    let startTouches = [], lastX = 0, lastY = 0, prevTwoFingerDist = 0;
    let startTime = 0, twoFingerMode = null, isForceClicked = false;
    let lastTapTime = 0, isDragging = false;

    function isUI(e) {
      return e.target.closest('#gear-btn') || e.target.closest('#drawer');
    }

    window.addEventListener('touchstart', (e) => {
      if (isUI(e)) return;
      e.preventDefault();

      startTouches = Array.from(e.touches);
      startTime = Date.now();
      lastX = e.touches[0].clientX;
      lastY = e.touches[0].clientY;
      twoFingerMode = null;

      if (e.touches.length === 1 && (Date.now() - lastTapTime < 280)) {
        isDragging = true;
        triggerHapticFeedback(true);
        ws.send(JSON.stringify({ a: "drag_start" }));
      }

      if (e.touches.length === 2) {
        prevTwoFingerDist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        );
      }
    }, { passive: false });

    window.addEventListener('touchmove', (e) => {
      if (isUI(e)) return;
      e.preventDefault();
      if (!ws || ws.readyState !== WebSocket.OPEN) return;

      const num = e.touches.length;

      if (num === 1) {
        const touch = e.touches[0];
        const force = touch.force !== undefined ? touch.force : 0;

        if (force >= forceThreshold && !isForceClicked) {
          isForceClicked = true;
          triggerHapticFeedback(true);
          ws.send(JSON.stringify({ a: "drag_start" }));
        } else if (force < (forceThreshold - 0.12) && isForceClicked) {
          isForceClicked = false;
          triggerHapticFeedback(false);
          ws.send(JSON.stringify({ a: "drag_end" }));
        }

        const dx = (touch.clientX - lastX) * sens;
        const dy = (touch.clientY - lastY) * sens;
        ws.send(JSON.stringify({ a: "move", dx, dy }));
        lastX = touch.clientX;
        lastY = touch.clientY;
      }
      else if (num === 2) {
        const curDist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        );
        const distDelta = curDist - prevTwoFingerDist;

        if (!twoFingerMode) {
          const moveY = Math.abs(e.touches[0].clientY - lastY);
          if (Math.abs(distDelta) > 8) {
            twoFingerMode = 'ZOOM';
            ws.send(JSON.stringify({ a: "pinch_start" }));
          } else if (moveY > 8) {
            twoFingerMode = 'SCROLL';
          }
        }

        if (twoFingerMode === 'ZOOM') {
          ws.send(JSON.stringify({ a: "pinch_delta", d: distDelta }));
          prevTwoFingerDist = curDist;
        } 
        else if (twoFingerMode === 'SCROLL') {
          const dy = (e.touches[0].clientY - lastY) * (scrollSpeed * 0.22);
          const dx = (e.touches[0].clientX - lastX) * (scrollSpeed * 0.22);
          ws.send(JSON.stringify({ a: "scroll", dx: dx, dy: dy }));
          lastX = e.touches[0].clientX;
          lastY = e.touches[0].clientY;
        }
      }
    }, { passive: false });

    window.addEventListener('touchend', (e) => {
      if (isUI(e)) return;
      e.preventDefault();
      if (!ws || ws.readyState !== WebSocket.OPEN) return;

      const count = startTouches.length;
      const duration = Date.now() - startTime;

      if (twoFingerMode === 'ZOOM') {
        ws.send(JSON.stringify({ a: "pinch_end" }));
        twoFingerMode = null;
      }

      if (isForceClicked) {
        isForceClicked = false;
        triggerHapticFeedback(false);
        ws.send(JSON.stringify({ a: "drag_end" }));
        startTouches = [];
        return;
      }

      if (isDragging) {
        isDragging = false;
        triggerHapticFeedback(false);
        ws.send(JSON.stringify({ a: "drag_end" }));
      }

      if (duration < 240 && e.changedTouches.length > 0) {
        const dist = Math.hypot(
          e.changedTouches[0].clientX - startTouches[0].clientX,
          e.changedTouches[0].clientY - startTouches[0].clientY
        );
        if (dist < 9) {
          if (count === 1) {
            triggerHapticFeedback(true);
            ws.send(JSON.stringify({ a: "click", b: "left" }));
            lastTapTime = Date.now();
          } else if (count === 2) {
            triggerHapticFeedback(true);
            ws.send(JSON.stringify({ a: "click", b: "right" }));
          } else if (count === 3) {
            triggerHapticFeedback(true);
            ws.send(JSON.stringify({ a: "click", b: "middle" }));
          } else if (count === 4) {
            triggerHapticFeedback(true);
            ws.send(JSON.stringify({ a: "gesture", type: "action_center" }));
          }
          startTouches = [];
          return;
        }
      }

      if (e.changedTouches.length > 0 && count >= 3) {
        const dy = e.changedTouches[0].clientY - startTouches[0].clientY;
        const dx = e.changedTouches[0].clientX - startTouches[0].clientX;

        if (count === 3) {
          if (Math.abs(dy) > 40 && Math.abs(dy) > Math.abs(dx)) {
            triggerHapticFeedback(true);
            ws.send(JSON.stringify({ a: "gesture", type: dy < 0 ? "task_view" : "show_desktop" }));
          } else if (Math.abs(dx) > 40) {
            triggerHapticFeedback(true);
            ws.send(JSON.stringify({ a: "gesture", type: dx < 0 ? "app_prev" : "app_next" }));
          }
        } else if (count === 4) {
          if (Math.abs(dx) > 40) {
            triggerHapticFeedback(true);
            ws.send(JSON.stringify({ a: "gesture", type: dx < 0 ? "desk_right" : "desk_left" }));
          } else if (Math.abs(dy) > 40) {
            triggerHapticFeedback(true);
            ws.send(JSON.stringify({ a: "gesture", type: dy < 0 ? "vol_up" : "vol_down" }));
          }
        }
      }
      startTouches = [];
    }, { passive: false });
  </script>
</body>
</html>
"""

async def handle_index(request):
    return web.Response(text=HTML_PAGE, content_type='text/html')

async def handle_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            try:
                data = json.loads(msg.data)
                a = data.get("a")

                if a == "move":
                    mouse.move(data["dx"], data["dy"])

                elif a == "scroll":
                    mouse.scroll(data.get("dx", 0), -data["dy"])

                elif a == "pinch_start":
                    zoom_engine.start_pinch()

                elif a == "pinch_delta":
                    zoom_engine.update_delta(data["d"])

                elif a == "pinch_end":
                    zoom_engine.end_pinch()

                elif a == "drag_start":
                    mouse.press(Button.left)

                elif a == "drag_end":
                    mouse.release(Button.left)

                elif a == "click":
                    btn = Button.left if data["b"] == "left" else (Button.right if data["b"] == "right" else Button.middle)
                    mouse.click(btn)

                elif a == "gesture":
                    t = data.get("type")
                    if t == "task_view":
                        with keyboard.pressed(Key.cmd): keyboard.tap(Key.tab)
                    elif t == "show_desktop":
                        with keyboard.pressed(Key.cmd): keyboard.tap('d')
                    elif t == "app_next":
                        with keyboard.pressed(Key.alt): keyboard.tap(Key.tab)
                    elif t == "app_prev":
                        with keyboard.pressed(Key.shift), keyboard.pressed(Key.alt): keyboard.tap(Key.tab)
                    elif t == "desk_right":
                        with keyboard.pressed(Key.ctrl), keyboard.pressed(Key.cmd): keyboard.tap(Key.right)
                    elif t == "desk_left":
                        with keyboard.pressed(Key.ctrl), keyboard.pressed(Key.cmd): keyboard.tap(Key.left)
                    elif t == "action_center":
                        with keyboard.pressed(Key.cmd): keyboard.tap('a')
                    elif t == "vol_up":
                        keyboard.tap(Key.media_volume_down)
                    elif t == "vol_down":
                        keyboard.tap(Key.media_volume_up)

            except Exception:
                pass
    return ws

def get_network_info():
    hostname = socket.gethostname().lower()
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    return hostname, ips

app = web.Application()
app.router.add_get('/', handle_index)
app.router.add_get('/ws', handle_ws)

if __name__ == '__main__':
    hostname, ips = get_network_info()
    print("=" * 60)
    print(" 🌟 AIRTRACK ACTIVE")
    print("=" * 60)
    print(" 📌 IF CONNECTED OVER WI-FI (Home / College):")
    print(f"    👉 http://{hostname}.local:5000\n")
    print(" 🔌 IF USING OFFLINE HOTSPOT (Option 2 in Launcher):")
    print("    👉 http://192.168.137.1:5000\n")
    print(" Available IPs on this machine:")
    for ip in ips:
        print(f"    • http://{ip}:5000")
    print("=" * 60)
    web.run_app(app, host='0.0.0.0', port=5000, print=False)