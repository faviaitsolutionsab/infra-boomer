#!/usr/bin/env python3
import json, os, sys, pathlib, re

argv_out = sys.argv[1] if len(sys.argv) > 1 else ""
argv_md  = sys.argv[2] if len(sys.argv) > 2 else ""

AUTHOR   = os.getenv("PR_AUTHOR", "").strip()
MENTIONS = os.getenv("MENTION_HANDLES", "").strip()
MARKER   = os.getenv("INPUT_COMMENT_MARKER", "<!-- infracost-comment -->").strip()

PING_AUTHOR   = os.getenv("PING_AUTHOR", "true").lower() in ("1","true","yes")
PING_MENTIONS = os.getenv("PING_MENTIONS", "false").lower() in ("1","true","yes")
COMMENT_TITLE = os.getenv("COMMENT_TITLE", "💸 Infracost Report").strip()

WS = os.getenv("GITHUB_WORKSPACE", "").rstrip("/")
WD = os.getenv("INFRACOST_WD", os.path.join(WS, ".github/fixtures/terraform") if WS else ".")
if MARKER.strip() == "<!-- infracost-comment -->":
    MARKER = f"<!-- infracost-comment:{WD} -->"
if not COMMENT_TITLE or COMMENT_TITLE.strip() == "💸 Infracost Report":
    COMMENT_TITLE = f"💸 Infracost Report for {WD}"
if os.getenv("PR_BASE_PRESENT", "").lower() in ("false", "0", "no"):
    COMMENT_TITLE = f"{COMMENT_TITLE} — 🆕 New folder"
PR_J = os.path.join(WD, ".infracost-pr.json")

CURRENCY = os.getenv("INFRACOST_CURRENCY", os.getenv("CURRENCY", "USD")).upper().strip()
FLAG_MAP = {"USD":"🇺🇸","EUR":"🇪🇺","GBP":"🇬🇧","INR":"🇮🇳","AUD":"🇦🇺","CAD":"🇨🇦","JPY":"🇯🇵","NZD":"🇳🇿","CHF":"🇨🇭","SEK":"🇸🇪"}
CURRENCY_FLAG = os.getenv("CURRENCY_FLAG", FLAG_MAP.get(CURRENCY, "💱")).strip()
SYMBOLS = {"USD":"$","EUR":"€","GBP":"£","INR":"₹","AUD":"A$","CAD":"C$","JPY":"¥","NZD":"NZ$","CHF":"CHF","SEK":"SEK"}
SYM = SYMBOLS.get(CURRENCY, CURRENCY)

WS = os.getenv("GITHUB_WORKSPACE", "").rstrip("/")
WD = os.getenv("INFRACOST_WD", os.path.join(WS, ".github/fixtures/terraform") if WS else ".")
PR_J = os.path.join(WD, ".infracost-pr.json")
BA_J = os.path.join(WD, ".infracost-base.json")

def first_file(paths):
    for p in paths:
        if p and os.path.isfile(p): return p
    return None

candidates_out = [argv_out, os.getenv("INFRACOST_OUT_PATH", "").strip(), os.path.join(WD, "infracost.out.json"), "infracost.out.json"]
OUT_PATH = first_file(candidates_out)

COMMENT_PATH = argv_md or os.getenv("INFRACOST_COMMENT_PATH", "").strip()
if not COMMENT_PATH:
    COMMENT_PATH = os.path.join(WD, "infracost_comment.md")

def to_float(x):
    try:
        if x in (None, "", "-", "null"): return 0.0
        return float(x)
    except Exception:
        s = re.sub(r"[^\d\.\-eE]", "", str(x))
        try:
            return float(s) if s else 0.0
        except Exception:
            return 0.0

def money(x):
    return f"{SYM}{x:,.2f}" if SYM in {"$","€","£","¥"} else f"{x:,.2f} {SYM}"

def money_hr(x):
    return f"{SYM}{x:.4f}" if SYM in {"$","€","£","¥"} else f"{x:.4f} {SYM}"

def arrow(x):
    if x > 0: return "🔺"
    if x < 0: return "🔻"
    return "⟷"

def sum_total_monthly_cost(path):
    if not path or not os.path.isfile(path): return None
    with open(path) as f: data = json.load(f)
    total = 0.0
    for p in data.get("projects", []):
        b = p.get("breakdown") or {}
        total += to_float(b.get("totalMonthlyCost"))
    return total

def read_diff_totals(path):
    if not path or not os.path.isfile(path): return None
    with open(path) as f: data = json.load(f)
    cur = fut = dlt = 0.0
    found = False
    for p in data.get("projects", []):
        d = p.get("diff") or {}
        if d:
            found = True
            cur += to_float(d.get("pastTotalMonthlyCost"))
            fut += to_float(d.get("totalMonthlyCost"))
            dlt += to_float(d.get("diffTotalMonthlyCost"))
    return (cur, fut, dlt) if found else None

totals = read_diff_totals(OUT_PATH)
if totals is None or (totals[0] == 0.0 and os.path.isfile(BA_J)):
    current = sum_total_monthly_cost(BA_J) or 0.0
    future  = sum_total_monthly_cost(PR_J) or 0.0
    delta = future - current
else:
    current, future, delta = totals

# Guard clause: skip comment if delta is very close to zero
if abs(delta) < 0.01:
    if os.getenv("INFRACOST_SILENT_SKIP", "").lower() in ("1","true","yes"):
        sys.exit(0)
    print("::notice::Infracost delta is zero → skipping PR comment.")
    sys.exit(0)

daily_current,  daily_future,  daily_delta  = current/30.0,  future/30.0,  delta/30.0
hourly_current, hourly_future, hourly_delta = current/730.0, future/730.0, delta/730.0
arr = arrow(delta)

lines = [MARKER]
if AUTHOR and PING_AUTHOR:
    lines.append(f"@{AUTHOR}")
if MENTIONS and PING_MENTIONS:
    lines.append(MENTIONS)
if (AUTHOR and PING_AUTHOR) or (MENTIONS and PING_MENTIONS):
    lines.append("")
lines.append(f"## 💸 Infracost for `{WD}` — {arr} {money(delta)}\n")
lines.append(f"{arr} Monthly delta: {CURRENCY_FLAG} {money(delta)}\n")
lines.append("| Period | Current 🟦 | Future 🟨 | Δ |")
lines.append("|--------|-----------:|-----------:|---:|")
lines.append(f"| Monthly | {money(current)} | {money(future)} | {arr} {money(delta)} |")
lines.append(f"| Daily   | {money(daily_current)} | {money(daily_future)} | {arr} {money(daily_delta)} |")
lines.append(f"| Hourly  | {money_hr(hourly_current)} | {money_hr(hourly_future)} | {arr} {money_hr(hourly_delta)} |")
lines.append("")
lines.append("_Estimates based on Terraform plan; actual cloud bills may vary._")
lines.append("")
lines.append("---")
lines.append("")

pathlib.Path(os.path.dirname(COMMENT_PATH) or ".").mkdir(parents=True, exist_ok=True)
with open(COMMENT_PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"✅ Wrote cost report → {COMMENT_PATH}")
print(f"ℹ️ Current(FROM base breakdown) = {money(current)}")
print(f"ℹ️ Future (FROM PR breakdown)   = {money(future)}")
print(f"ℹ️ Also checked diff JSON       = {OUT_PATH}" if OUT_PATH else "ℹ️ No diff JSON provided; used breakdown files only.")