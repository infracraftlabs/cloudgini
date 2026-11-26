"""Builds the CloudGini LinkedIn carousel (1080x1350 PNGs) from HTML + real app screenshots.
Run: python3 social/make-carousel.py   (needs Google Chrome; screenshots in social/shots/)."""
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "carousel"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H, PAD = 1080, 1350, 64
TOTAL = 7

CSS = f"""
* {{ box-sizing: border-box; margin: 0; }}
body {{ width: {W}px; height: {H}px; font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; color: #0f172a;
       background: #f8fafc; padding: {PAD}px; display: flex; flex-direction: column; }}
.top {{ display: flex; justify-content: space-between; align-items: center; font-size: 22px; color: #2259d1; font-weight: 700; }}
.top span {{ color: #64748b; font-weight: 500; }}
.kicker {{ margin-top: 40px; font-size: 22px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: #2259d1; }}
h1 {{ margin-top: 10px; font-size: 54px; line-height: 1.1; letter-spacing: -.02em; }}
p.lead {{ margin-top: 18px; font-size: 27px; line-height: 1.4; color: #334155; }}
.shot {{ margin-top: 30px; border-radius: 18px; border: 2px solid #e2e8f0; box-shadow: 0 10px 30px rgba(15,23,42,.10);
        background-repeat: no-repeat; background-color: white; }}
.foot {{ margin-top: auto; display: flex; justify-content: space-between; font-size: 20px; color: #64748b; }}
.tag {{ display: inline-block; padding: 4px 12px; border-radius: 8px; font-size: 20px; font-weight: 600; }}
.box {{ border-radius: 16px; border: 2px solid #cbd5e1; background: white; padding: 26px 26px; font-size: 25px; line-height: 1.4; }}
.box b {{ display: block; font-size: 29px; margin-bottom: 4px; }}
.arrow {{ text-align: center; font-size: 40px; color: #94a3b8; line-height: 1; margin: 14px 0; }}
.state {{ display: flex; align-items: center; gap: 18px; }}
.pill {{ padding: 22px 28px; border-radius: 16px; font-size: 34px; font-weight: 700; min-width: 290px; text-align: center; }}
.note {{ font-size: 26px; color: #475569; line-height: 1.35; }}
ul.rails {{ margin-top: 44px; padding-left: 0; list-style: none; display: flex; flex-direction: column; gap: 18px; }}
ul.rails li {{ font-size: 30px; line-height: 1.35; padding-left: 44px; position: relative; }}
ul.rails li::before {{ content: '✓'; position: absolute; left: 0; color: #15803d; font-weight: 800; }}
"""


def page(n, body):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="top">CloudGini <span>InfraCraft Labs · AI Lab</span></div>
{body}
<div class="foot"><span>Prototype · simulated demo data</span><span>{n} / {TOTAL}</span></div></body></html>"""


def shot(name, x, y, w, h, width=W - 2 * PAD, page_w=660):
    """Crop region (x, y, w, h) in CSS pixels of a page screenshot taken at page_w CSS pixels wide."""
    f = width / w
    return (f'<div class="shot" style="width:{width}px;height:{round(h * f)}px;margin-left:auto;margin-right:auto;'
            f'background-image:url(../shots/{name}.png);'
            f'background-size:{round(page_w * f)}px auto;background-position:-{round(x * f)}px -{round(y * f)}px"></div>')


def pill(text, bg, fg):
    return f'<div class="pill" style="background:{bg};color:{fg}">{text}</div>'


slides = []
# 1. Cover: the lifecycle
chain = "".join(
    f'<div class="state">{pill(s, bg, fg)}<div class="note">{note}</div></div>' + ('<div class="arrow">↓</div>' if i < 4 else "")
    for i, (s, bg, fg, note) in enumerate([
        ("Detected", "#d9eaff", "#1c47a6", "a rule fires, with its evidence attached"),
        ("Reviewed", "#ede9fe", "#6d28d9", "a person reads the evidence"),
        ("Approved", "#fef3c7", "#92400e", "after a dry-run shows exactly what changes"),
        ("Executed", "#ffedd5", "#9a3412", "one of five allow-listed actions"),
        ("Verified", "#dcfce7", "#166534", "only after a fresh read of the resource"),
    ]))
slides.append(page(1, f"""
<div class="kicker">Cloud cost · cleanup · security</div>
<h1>When is a cloud fix actually done?</h1>
<p class="lead">CloudGini only says "verified" after it has looked again.</p>
<div style="margin-top:56px">{chain}</div>
<div style="margin-top:48px" class="note">Anything else ends as <b style="color:#b91c1c">failed</b>, <b>rejected</b> or
<b style="color:#c2410c">requires manual review</b>, never silently "fixed".</div>"""))

# 2. Design: architecture
def col(title, lines, border="#cbd5e1"):
    return f'<div class="box" style="border-color:{border}"><b>{title}</b>{"<br>".join(lines)}</div>'
slides.append(page(2, f"""
<div class="kicker">Design</div>
<h1>Read first. Change little. Check after.</h1>
<div style="margin-top:48px;display:grid;grid-template-columns:1fr 1fr;gap:18px">
  {col("Simulated provider", ["41 synthetic resources with", "planted issues, for the demo"])}
  {col("Google Cloud adapter", ["Asset Inventory, Monitoring,", "billing export, SCC · read-only"])}
</div>
<div class="arrow">↓</div>
{col("Rules engine", ["Cost and right-sizing · unused-resource cleanup · 10 security checks.", "Every item carries metrics, window, checks, confidence and risk."], "#2259d1")}
<div class="arrow">↓</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
  {col("Recommendations", ["one lifecycle, labelled", "real/simulated, estimated/verified"])}
  {col("Remediation", ["5 allow-listed actions:", "dry-run → approve → execute → verify"])}
</div>
<div class="arrow">↓</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
  {col("Append-only audit log", ["every step, including refusals"])}
  {col("Assistant", ["explains the analysis; no tools,", "works without a model key"])}
</div>
<div style="margin-top:36px" class="note">FastAPI + PostgreSQL · Next.js + Recharts · Terraform + Cloud Run</div>"""))

# 3. Overview
slides.append(page(3, f"""
<div class="kicker">Functionality · overview</div>
<h1>Every number says where it came from</h1>
<p class="lead">Simulated data is labelled. Savings stay "estimated" until billing proves them.</p>
{shot("n-overview", 22, 291, 616, 539, width=880)}"""))

# 4. Evidence
slides.append(page(4, f"""
<div class="kicker">Functionality · evidence</div>
<h1>A recommendation shows its working</h1>
<p class="lead">Metric, source, window, and how the saving was worked out.</p>
{shot("n-evidence", 24, 432, 612, 283, width=880)}
{shot("n-evidence", 24, 1262, 612, 190, width=880)}"""))

# 5. Dry-run
slides.append(page(5, f"""
<div class="kicker">Functionality · dry-run</div>
<h1>See the change before it happens</h1>
<p class="lead">Steps, before and after, preconditions and rollback. Irreversible actions need the resource name typed to approve.</p>
{shot("n-remediation", 41, 492, 578, 306)}"""))

# 6. Verify
slides.append(page(6, f"""
<div class="kicker">Functionality · verification</div>
<h1>"Done" means checked again</h1>
<p class="lead">CloudGini re-reads the resource. In the demo another tool reverts a firewall change, so it ends as failed.</p>
{shot("n-remediation", 41, 1421, 578, 551, width=830)}"""))

# 7. Guard rails and status
slides.append(page(7, """
<div class="kicker">Guard rails and status</div>
<h1>What it will never do, and what isn't proven yet</h1>
<ul class="rails">
  <li>Read-only by default; remediation is switched on per account</li>
  <li>Production and unlabelled resources are never changed</li>
  <li>No deletion of data, no shell, no arbitrary API calls</li>
  <li>Admins can't remediate; operators can't change settings</li>
</ul>
<div class="box" style="margin-top:40px;border-color:#f59e0b;background:#fffbeb">
  <b>Prototype</b>30 automated tests pass on the simulated estate. The Google Cloud adapter has not yet been run
  against a live project, and verified savings aren't implemented.</div>
<p class="lead" style="margin-top:36px"><b>Code:</b> github.com/infracraftlabs/cloudgini<br><b>Page:</b> infracraftlabs.com/lab/cloudgini</p>"""))

OUT.mkdir(exist_ok=True)
for i, html in enumerate(slides, 1):
    src = OUT / f"slide-{i}.html"
    src.write_text(html)
    subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=1",
                    f"--window-size={W},{H}", f"--screenshot={OUT / f'slide-{i}.png'}", src.as_uri()],
                   check=True, capture_output=True)
    src.unlink()
print(f"wrote {len(slides)} slides to {OUT}")
