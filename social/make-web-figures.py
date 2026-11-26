"""Figures for the CloudGini Lab page on infracraftlabs.com (720 CSS px wide, rendered at 2x).
Run: python3 social/make-web-figures.py   (needs Google Chrome; screenshots in social/shots/).
Output: social/web/*.png, copied to the site's public/images/lab/cloudgini/."""
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "web"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W = 720

CSS = """
* { box-sizing: border-box; margin: 0; }
body { width: 720px; font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; color: #0f172a; background: #f8fafc; padding: 22px; }
.k { font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: #2259d1; }
h3 { font-size: 20px; margin: 4px 0 14px; letter-spacing: -.01em; }
.box { border-radius: 10px; border: 1.5px solid #cbd5e1; background: white; padding: 10px 12px; font-size: 13px; line-height: 1.4; color: #334155; }
.box b { display: block; font-size: 14px; color: #0f172a; margin-bottom: 2px; }
.g2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.ar { text-align: center; color: #94a3b8; font-size: 18px; line-height: 1; margin: 5px 0; }
.foot { margin-top: 12px; font-size: 12px; color: #64748b; }
.row { display: flex; align-items: center; gap: 6px; }
.pill { flex: 1; text-align: center; border-radius: 10px; padding: 10px 4px 9px; font-weight: 700; font-size: 14px; }
.pill small { display: block; font-weight: 500; font-size: 11px; margin-top: 3px; line-height: 1.3; opacity: .9; }
.arr { color: #94a3b8; font-size: 16px; }
.shot { border-radius: 10px; border: 1px solid #e2e8f0; box-shadow: 0 4px 14px rgba(15,23,42,.08); background-repeat: no-repeat; background-color: white; }
"""


def page(body):
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{body}</body></html>'


def box(t, lines, border="#cbd5e1"):
    return f'<div class="box" style="border-color:{border}"><b>{t}</b>{"<br>".join(lines)}</div>'


def shot(name, x, y, w, h, width=W - 44, page_w=660):
    f = width / w
    return (f'<div class="shot" style="width:{width}px;height:{round(h * f)}px;background-image:url(../shots/{name}.png);'
            f'background-size:{round(page_w * f)}px auto;background-position:-{round(x * f)}px -{round(y * f)}px"></div>')


FIGS = {
    "design": (page(f"""<div class="k">Design</div><h3>Read first, change little, check after</h3>
<div class="g2">{box("Simulated provider", ["41 synthetic resources with planted issues"])}
{box("Google Cloud adapter (read-only)", ["Asset Inventory, Monitoring, billing export, SCC"])}</div>
<div class="ar">↓</div>
{box("Rules engine", ["Cost and right-sizing · unused-resource cleanup · 10 security checks. Each item carries metrics, window, checks, confidence and risk."], "#2259d1")}
<div class="ar">↓</div>
<div class="g2">{box("Recommendations", ["one lifecycle; labelled real/simulated and estimated/verified"])}
{box("Remediation", ["5 allow-listed actions: dry-run → approve → execute → verify"])}</div>
<div class="ar">↓</div>
<div class="g2">{box("Append-only audit log", ["every step, including refusals"])}
{box("Assistant", ["explains the analysis; no tools; works without a model key"])}</div>
<div class="foot">FastAPI + PostgreSQL · Next.js + Recharts · Terraform + Cloud Run</div>"""), 508),
    "lifecycle": (page("""<div class="k">Recommendation lifecycle</div><h3>"Verified" only after CloudGini looks again</h3>
<div class="row">
<div class="pill" style="background:#d9eaff;color:#1c47a6">Detected<small>rule fires, evidence attached</small></div><span class="arr">→</span>
<div class="pill" style="background:#ede9fe;color:#6d28d9">Reviewed<small>a person reads it</small></div><span class="arr">→</span>
<div class="pill" style="background:#fef3c7;color:#92400e">Approved<small>after a dry-run</small></div><span class="arr">→</span>
<div class="pill" style="background:#ffedd5;color:#9a3412">Executed<small>allow-listed action</small></div><span class="arr">→</span>
<div class="pill" style="background:#dcfce7;color:#166534">Verified<small>fresh read matches</small></div></div>
<div class="foot" style="font-size:13px;color:#475569">Otherwise it ends as <b style="color:#b91c1c">failed</b>, <b>rejected</b> or
<b style="color:#c2410c">requires manual review</b> (for example when metrics are missing, which also means no savings figure).</div>"""), 212),
    "dry-run": (page(f"""<div class="k">Dry-run (simulated demo)</div><h3>Every change is planned and shown before approval</h3>
{shot("n-remediation", 41, 492, 578, 306)}"""), 440),
    "verification": (page(f"""<div class="k">Verification (simulated demo)</div><h3>A change another tool reverts ends as failed, not fixed</h3>
{shot("n-remediation", 41, 1421, 578, 551)}"""), 760),
}

OUT.mkdir(exist_ok=True)
for name, (html, h) in FIGS.items():
    src = OUT / f"{name}.html"
    src.write_text(html)
    subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=2",
                    f"--window-size={W},{h}", f"--screenshot={OUT / f'cloudgini-{name}.png'}", src.as_uri()],
                   check=True, capture_output=True)
    src.unlink()
print("wrote", ", ".join(f"cloudgini-{n}.png" for n in FIGS))
