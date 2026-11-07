"""Render the architecture diagrams from HTML with headless Chrome/Edge.

    python docs/diagram/build.py

Outputs:
    docs/architecture.png           solution architecture (AWS, GPU, S3), used in the docs
    docs/event-driven.png           event-driven view: containers and events only, large logos

Logos live in assets/logos. Monochrome Simple Icons SVGs get their brand colour here.
Intermediate HTML files are written next to this script (git-ignored).
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOGOS = ROOT / "assets" / "logos"

BRAND_FILL = {
    "nats": "#27AAE1",
    "huggingface": "#FFB000",
    "fastapi": "#009688",
    "caddy": "#1F88C0",
    "whatsapp": "#25D366",
    "nvidia": "#76B900",
}

# Line icons (24x24, black stroke) for things that have no logo.
_ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#111" '
         'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{}</svg>')
ICONS = {
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8"/>',
    "wave": '<path d="M3 12h2M7 8v8M11 5v14M15 9v6M19 7v10M21 12h0"/>',
    "classify": '<circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="12" r="2"/>'
                '<circle cx="19" cy="19" r="2"/><path d="M7 12h10M7 12c5 0 5-7 10-7M7 12c5 0 5 7 10 7"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
    "kiosk": '<rect x="5" y="3" width="14" height="11" rx="1.5"/><path d="M9 21h6M12 14v7"/><path d="M8 7h8M8 10h5"/>',
    "headset": '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="14" width="4" height="6" rx="1.5"/>'
               '<rect x="17" y="14" width="4" height="6" rx="1.5"/><path d="M19 20c0 1-2 2-5 2"/>',
    "relay": '<path d="M4 8h13l-3-3M20 16H7l3 3"/>',
    "broom": '<path d="M14 3l-4 9M7 12h8l2 9H5z"/><path d="M9 16v5M13 16v5"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3M15 8l2 2"/>',
    "box": '<path d="M3 7l9-4 9 4-9 4zM3 7v10l9 4 9-4V7M12 11v10"/>',
    "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
}


def logo(name: str) -> str:
    for ext, mime in (("svg", "image/svg+xml"), ("png", "image/png")):
        path = LOGOS / f"{name}.{ext}"
        if path.exists():
            data = path.read_bytes()
            if ext == "svg" and name in BRAND_FILL:
                data = data.replace(b"<svg ", f'<svg fill="{BRAND_FILL[name]}" '.encode(), 1)
            return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    raise FileNotFoundError(name)


def icon(name: str) -> str:
    svg = _ICON.format(ICONS[name])
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"


def label(x, y, text, anchor="c", cls="lab"):
    shift = {"c": "-50%", "l": "0", "r": "-100%"}[anchor]
    return f'<div class={cls} style="left:{x}px;top:{y}px;transform:translate({shift},-50%)">{text}</div>'


def wire(points, dashed=False, arrow=True):
    d = " ".join(f"{x},{y}" for x, y in points)
    dash = ' stroke-dasharray="8 6"' if dashed else ""
    head = ' marker-end="url(#a)"' if arrow else ""
    return f'<polyline points="{d}" fill="none" stroke="#111" stroke-width="2.4"{dash}{head}/>'


def page(width, height, css, body, wires) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Sma3ni architecture</title>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; background: #fff; }}
  body {{ width: {width}px; height: {height}px; position: relative; overflow: hidden;
         font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: #111; }}
  h1 {{ position: absolute; left: 40px; top: 26px; margin: 0; font-size: 30px; font-weight: 700; letter-spacing: -.3px; }}
  h1 span {{ font-weight: 400; color: #555; font-size: 20px; margin-left: 14px; }}
  svg.wires {{ position: absolute; left: 0; top: 0; z-index: 1; }}
  .zone {{ position: absolute; border-radius: 14px; z-index: 0; }}
  .node, .box, .bus, .client, .lab, .ev, .legend {{ z-index: 2; }}
  .zone .cap {{ position: absolute; left: 14px; top: -16px; background: #fff; padding: 0 10px;
               display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; }}
  .lab {{ position: absolute; background: #fff; padding: 1px 6px; font-size: 12px; color: #111;
         border-radius: 4px; white-space: nowrap; line-height: 1.3; text-align: center; }}
  {css}
</style></head>
<body>
<svg class=wires width="{width}" height="{height}">
  <defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0 0L10 5L0 10z" fill="#111"/></marker></defs>
  {''.join(wires)}
</svg>
{body}
</body></html>"""


# --------------------------------------------------------------------------- 1. solution architecture
def solution() -> tuple[str, int, int]:
    W, H = 1920, 1240
    L = logo

    def node(x, y, w, h, logos, title, lines, cls=""):
        imgs = "".join(f'<img src="{src}" alt="">' for src in logos)
        body = "".join(f"<div class=l>{t}</div>" for t in lines)
        return (f'<div class="node {cls}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px">'
                f'<div class=logos>{imgs}</div><div class=t>{title}</div>{body}</div>')

    nodes = [
        node(40, 140, 240, 90, [icon("globe"), icon("mic")], "Citizen web page", ["voice note + consent"]),
        node(40, 260, 240, 90, [L("whatsapp")], "WhatsApp gateway", ["API key, intake scope"]),
        node(40, 380, 240, 90, [icon("kiosk")], "Kiosk / call centre", ["API key, intake scope"]),
        node(40, 500, 240, 90, [icon("headset")], "Agent console", ["API key, agent scope"]),
        node(40, 860, 240, 90, [L("huggingface")], "Hugging Face Hub", ["Morocco-MTNRA-Labs weights"]),
        node(960, 140, 240, 120, [L("s3")], "Amazon S3", ["temporary audio", "SSE-KMS, public access blocked", "lifecycle: expire after 7 days"]),
        node(1600, 140, 260, 120, [icon("key")], "IAM instance role", ["s3:Get/Put/DeleteObject", "on the audio prefix only", "no static access keys"]),
        node(380, 360, 180, 130, [L("caddy")], "Caddy", ["automatic TLS, HSTS, CSP", "12 MB upload limit"]),
        node(640, 360, 240, 130, [L("fastapi")], "api (FastAPI)", ["scoped API keys", "audio validation", "answers 202 in ms"]),
        node(1260, 360, 200, 130, [icon("broom")], "janitor", ["purges audio > 7 days", "recovers stuck", "requests"]),
        node(640, 580, 240, 140, [L("postgresql")], "PostgreSQL 17", ["requests, history", "outbox, routing rules", "audit, encrypted contacts"]),
        node(960, 580, 200, 140, [icon("relay")], "relay", ["outbox to NATS", "LISTEN/NOTIFY", "Nats-Msg-Id dedupe"]),
        node(1260, 580, 200, 140, [L("nats")], "NATS JetStream", ["durable stream on disk", "explicit ack, retries", "backoff 5 s to 10 min"]),
        node(380, 840, 180, 130, [L("huggingface"), icon("box")], "models volume", ["HF cache, read-only", "workers run offline"]),
        node(900, 820, 250, 170, [L("mistral"), icon("classify")], "nlp-worker",
             ["<b>LIDstral-Arabic</b>: dialect", "(Darija, Hassaniya, MSA...)", "rule-based classification:", "service + priority"], "ml"),
        node(1210, 820, 250, 170, [L("mistral"), icon("wave"), L("nvidia")], "asr-worker (GPU)",
             ["<b>Voxtral-Mini-4B-Realtime-Arabic</b>", "Darija speech to text", "CUDA, bf16, one note at a time"], "ml"),
    ]
    wires = [
        wire([(280, 185), (300, 185), (300, 545), (280, 545)], arrow=False),
        wire([(280, 305), (300, 305)], arrow=False),
        wire([(280, 425), (300, 425)], arrow=False),
        wire([(300, 425), (380, 425)]),
        wire([(560, 425), (640, 425)]),
        wire([(820, 360), (820, 200), (960, 200)]),
        wire([(760, 490), (760, 580)]),
        wire([(1300, 360), (1300, 230), (1200, 230)]),
        wire([(1360, 490), (1360, 535), (850, 535), (850, 580)]),
        wire([(880, 650), (960, 650)]),
        wire([(1160, 650), (1260, 650)]),
        wire([(1380, 720), (1380, 820)], dashed=True),
        wire([(1300, 720), (1300, 770), (1025, 770), (1025, 820)], dashed=True),
        wire([(1460, 900), (1530, 900), (1530, 170), (1200, 170)]),
        wire([(1025, 990), (1025, 1070)], arrow=False),
        wire([(1335, 990), (1335, 1070), (760, 1070)], arrow=False),
        wire([(760, 1070), (760, 720)]),
        wire([(280, 905), (380, 905)]),
    ]
    labels = [
        label(340, 410, "HTTPS"), label(600, 410, "proxy"), label(890, 186, "PUT audio"),
        label(1250, 216, "DELETE"), label(1545, 520, "GET audio", "l"),
        label(770, 535, "one transaction:<br>request + event", "r"),
        label(1100, 535, "stuck requests"), label(920, 636, "NOTIFY"), label(1210, 636, "publish"),
        label(1390, 790, "request.received", "l"), label(1160, 770, "request.transcribed"),
        label(1050, 1070, "transcript, dialect, service, priority + next event"),
        label(330, 890, "models job<br>(once)"),
    ]
    legend = (
        '<div class=legend>'
        '<svg width="46" height="12"><line x1="0" y1="6" x2="40" y2="6" stroke="#111" stroke-width="2"/>'
        '<path d="M40 1l6 5-6 5z" fill="#111"/></svg> direct call or write'
        '<svg width="46" height="12"><line x1="0" y1="6" x2="40" y2="6" stroke="#111" stroke-width="2" stroke-dasharray="7 5"/>'
        '<path d="M40 1l6 5-6 5z" fill="#111"/></svg> event pulled from NATS (explicit ack)'
        '<span class=sep></span>Internal Docker network: only Caddy (80/443) and S3 (VPC endpoint) are reachable.'
        '</div>'
    )
    css = """
  .aws { left: 320px; top: 100px; width: 1570px; height: 1060px; border: 2px dashed #232F3E; }
  .ec2 { left: 350px; top: 300px; width: 1150px; height: 840px; border: 2px solid #c9c9c9; background: #fafafa; }
  .ec2 .cap { border: 2px solid #c9c9c9; border-radius: 8px; top: -18px; padding: 4px 10px; }
  .zone .cap img { height: 24px; }
  .node { position: absolute; background: #fff; border: 1.6px solid #111; border-radius: 10px; padding: 10px 12px; }
  .node.ml { border-width: 2.4px; }
  .logos { display: flex; gap: 8px; align-items: center; height: 30px; margin-bottom: 4px; }
  .logos img { height: 28px; max-width: 64px; object-fit: contain; }
  .t { font-weight: 700; font-size: 15px; margin-bottom: 2px; }
  .l { font-size: 12.5px; color: #333; line-height: 1.35; }
  .legend { position: absolute; left: 40px; top: 1186px; display: flex; align-items: center; gap: 10px; font-size: 13px; color: #333; }
  .legend svg { margin-left: 14px; }
  .legend .sep { width: 1px; height: 18px; background: #ccc; margin: 0 10px; }
"""
    body = (
        '<h1>Sma3ni<span>voice desk for citizens in Darija: solution architecture (AWS, GPU)</span></h1>'
        f'<div class="zone aws"><div class=cap><img src="{L("aws")}" alt="">AWS region (private VPC)</div></div>'
        f'<div class="zone ec2"><div class=cap><img src="{L("docker")}" alt=""><img src="{L("nvidia")}" alt="">'
        'EC2 g6.2xlarge (NVIDIA L4, 24 GB) · Docker Compose</div></div>'
        + "".join(nodes) + "".join(labels) + legend
    )
    return page(W, H, css, body, wires), W, H


# --------------------------------------------------------------------------- 2. event-driven view
def event_driven() -> tuple[str, int, int]:
    W, H = 1920, 1080
    L = logo
    whale = L("docker")

    def box(x, y, w, h, logos, name, cls=""):
        big = "big" if len(logos) == 1 else ("mid" if len(logos) == 2 else "small")
        imgs = "".join(f'<img src="{src}" alt="">' for src in logos)
        badge = f'<img class=whale src="{whale}" alt="">' if "ext" not in cls else ""
        return (f'<div class="box {cls}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px">{badge}'
                f'<div class="lg {big}">{imgs}</div><div class=n>{name}</div></div>')

    def client(x, y, src, name):
        return (f'<div class=client style="left:{x}px;top:{y}px"><img src="{src}" alt="">'
                f'<div class=n>{name}</div></div>')

    chips = "".join(f"<span class=chip>{s}</span>" for s in (
        "request.received", "request.transcribed", "request.routed", "request.status_changed"))
    bus = (f'<div class=bus style="left:1030px;top:470px;width:590px;height:190px">'
           f'<img class=whale src="{whale}" alt="">'
           f'<div class=buslogo><img src="{L("nats")}" alt=""><div class=n>NATS JetStream</div></div>'
           f'<div class=chips>{chips}</div></div>')

    body = (
        '<h1>Sma3ni<span>event-driven architecture</span></h1>'
        f'<div class="zone frame"><div class=cap><img src="{whale}" alt="">docker compose</div></div>'
        + client(70, 150, icon("mic"), "Citizen")
        + client(70, 330, L("whatsapp"), "WhatsApp")
        + client(70, 510, icon("headset"), "Agents")
        + box(320, 160, 170, 190, [L("caddy")], "caddy")
        + box(570, 160, 170, 190, [L("fastapi")], "api")
        + box(570, 470, 170, 190, [L("postgresql")], "postgres")
        + box(800, 470, 170, 190, [icon("relay")], "relay")
        + bus
        + box(320, 790, 170, 190, [icon("broom")], "janitor")
        + box(1030, 790, 200, 190, [L("mistral"), icon("classify")], "nlp-worker", "ml")
        + box(1260, 790, 140, 190, [icon("bell")], "notifier", "planned")
        + box(1430, 790, 190, 190, [L("mistral"), icon("wave"), L("nvidia")], "asr-worker", "ml")
        + box(1720, 790, 170, 190, [L("s3")], "Amazon S3", "ext")
        + label(1145, 725, "request.transcribed", "l", "ev")
        + label(1340, 725, "request.routed", "l", "ev")
        + label(1535, 725, "request.received", "l", "ev")
    )
    wires = [
        wire([(200, 205), (255, 205), (255, 565), (200, 565)], arrow=False),
        wire([(200, 385), (255, 385)], arrow=False),
        wire([(255, 255), (320, 255)]),
        wire([(490, 255), (570, 255)]),                              # caddy -> api
        wire([(655, 350), (655, 470)]),                              # api -> postgres (outbox)
        wire([(740, 205), (1805, 205), (1805, 790)]),                # api -> s3
        wire([(740, 565), (800, 565)]),                              # postgres -> relay
        wire([(970, 565), (1030, 565)]),                             # relay -> nats
        wire([(1130, 660), (1130, 790)], dashed=True),               # nats -> nlp
        wire([(1330, 660), (1330, 790)], dashed=True),               # nats -> notifier
        wire([(1525, 660), (1525, 790)], dashed=True),               # nats -> asr
        wire([(1620, 885), (1720, 885)]),                            # asr -> s3
        wire([(1130, 980), (1130, 1020)], arrow=False),              # nlp -> postgres
        wire([(1525, 980), (1525, 1020), (655, 1020)], arrow=False),  # asr -> postgres
        wire([(655, 1020), (655, 660)]),
        wire([(490, 885), (605, 885), (605, 660)]),                  # janitor -> postgres
    ]
    css = """
  .frame { left: 280px; top: 120px; width: 1380px; height: 930px; border: 2.4px solid #1D63ED; background: #f7faff; }
  .frame .cap { font-size: 22px; color: #1D63ED; top: -26px; background: #fff; }
  .frame .cap img { height: 44px; }
  .client { position: absolute; width: 130px; text-align: center; }
  .client img { width: 92px; height: 92px; display: block; margin: 0 auto 8px; }
  .client .n { font-size: 19px; font-weight: 700; }
  .box { position: absolute; background: #fff; border: 2.4px solid #111; border-radius: 16px;
         display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; }
  .box.planned { border-style: dashed; }
  .box.ext { border-color: #111; }
  .box .whale, .bus .whale { position: absolute; top: -14px; right: -14px; width: 34px; height: 34px;
         background: #fff; border-radius: 50%; }
  .lg { display: flex; align-items: center; justify-content: center; gap: 8px; }
  .lg.big img { width: 100px; height: 100px; object-fit: contain; }
  .lg.mid img { width: 70px; height: 70px; object-fit: contain; }
  .lg.small img { width: 50px; height: 50px; object-fit: contain; }
  .box .n { font-size: 20px; font-weight: 700; font-family: Consolas, "SFMono-Regular", monospace; }
  .bus { position: absolute; background: #fff; border: 3px solid #111; border-radius: 16px;
         display: flex; align-items: center; gap: 22px; padding: 0 22px; }
  .buslogo { text-align: center; }
  .buslogo img { width: 110px; height: 110px; }
  .buslogo .n { font-size: 20px; font-weight: 700; margin-top: 6px; white-space: nowrap; }
  .chips { display: grid; grid-template-columns: 1fr; gap: 8px; }
  .chip { font-family: Consolas, "SFMono-Regular", monospace; font-size: 16px; border: 1.6px solid #111;
          border-radius: 999px; padding: 4px 14px; background: #fff; white-space: nowrap; }
  .ev { position: absolute; font-family: Consolas, "SFMono-Regular", monospace; font-size: 15px;
        background: #f7faff; padding: 0 4px; white-space: nowrap; }
"""
    return page(W, H, css, body, wires), W, H


def find_browser() -> str | None:
    candidates = [
        os.environ.get("CHROME"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser"),
    ]
    return next((c for c in candidates if c and Path(c).exists()), None)


def render(name: str, html: str, width: int, height: int, browser: str | None) -> None:
    src = HERE / f"{name}.html"
    src.write_text(html, encoding="utf-8")
    if not browser:
        print(f"wrote {src.relative_to(ROOT)} (no Chrome/Edge found, screenshot it manually)")
        return
    out = ROOT / "docs" / f"{name}.png"
    subprocess.run([
        browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
        f"--window-size={width},{height}", f"--screenshot={out}", src.as_uri(),
    ], check=True, capture_output=True, timeout=60)
    print(f"wrote {out.relative_to(ROOT)}")


def main() -> int:
    browser = find_browser()
    for name, builder in (("architecture", solution), ("event-driven", event_driven)):
        html, w, h = builder()
        render(name, html, w, h, browser)
    return 0


if __name__ == "__main__":
    sys.exit(main())
