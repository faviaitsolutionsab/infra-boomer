#!/usr/bin/env python3
import json
import os
import re
from html import escape
from pathlib import Path
from typing import Optional, List, Dict, Any
import requests

GITHUB_API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
REPO = os.environ["GITHUB_REPOSITORY"]
OWNER, REPO_NAME = REPO.split("/", 1)
TOKEN = os.environ["GITHUB_TOKEN"]
EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME", "")
EVENT_PATH = os.environ.get("GITHUB_EVENT_PATH", "")
RUN_ID = os.environ.get("GITHUB_RUN_ID", "")
REPO_OWNER_FOR_URL = os.environ.get("GITHUB_REPOSITORY_OWNER", OWNER)
GITHUB_SHA = os.environ.get("GITHUB_SHA", "")
PR_COMMENT_MARKER = os.environ.get("PR_COMMENT_MARKER", ".")
TF_ACTIONS_WORKING_DIR = os.environ.get("TF_ACTIONS_WORKING_DIR", ".")
GITHUB_ACTOR = os.environ.get("GITHUB_ACTOR", "")
GITHUB_WORKFLOW = os.environ.get("GITHUB_WORKFLOW", "")
TFLINT_OUTPUT = os.environ.get("TFLINT_OUTPUT", "")
PR_DELETE_COMMENT = os.environ.get("PR_DELETE_COMMENT", "false").lower() == "true"

SEV_EMOJI = {"error": "❌", "warning": "⚠️", "notice": "ℹ️", "info": "ℹ️"}
SEV_WEIGHT = {"error": 3, "warning": 2, "notice": 1, "info": 1}
LINE_RE = re.compile(
    r"""^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+):\s*
        (?P<level>[A-Za-z]+)\s*-\s*
        (?P<msg>.*?)
        (?:\s*\((?P<rule>[^)]+)\))?
        \s*$""",
    re.VERBOSE,
)
SESSION = requests.Session()
SESSION.headers.update(
    {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "tflint-pr-comment/py",
    }
)

def gh_headers() -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def get_pr_number() -> Optional[int]:
    if not EVENT_PATH or not Path(EVENT_PATH).is_file():
        return None
    with open(EVENT_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if "pull_request" in payload and "number" in payload:
        return int(payload["number"])
    return None

def list_all_comments(pr_number: int) -> List[dict]:
    comments: List[dict] = []
    page = 1
    while True:
        url = f"{GITHUB_API}/repos/{OWNER}/{REPO_NAME}/issues/{pr_number}/comments"
        r = SESSION.get(url, params={"per_page": 100, "page": page}, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        comments.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return comments

def find_existing_comment_id(pr_number: int, marker: str) -> Optional[int]:
    hidden = f"<!-- tflint:{marker} -->"
    for c in list_all_comments(pr_number):
        body = c.get("body") or ""
        if hidden in body or marker in body:
            return c["id"]
    return None

def delete_comment(comment_id: int) -> None:
    url = f"{GITHUB_API}/repos/{OWNER}/{REPO_NAME}/issues/comments/{comment_id}"
    r = SESSION.delete(url, timeout=30)
    if r.status_code not in (204, 404):
        r.raise_for_status()

def update_comment(comment_id: int, body: str) -> None:
    url = f"{GITHUB_API}/repos/{OWNER}/{REPO_NAME}/issues/comments/{comment_id}"
    r = SESSION.patch(url, json={"body": body}, timeout=30)
    r.raise_for_status()

def create_comment(pr_number: int, body: str) -> None:
    url = f"{GITHUB_API}/repos/{OWNER}/{REPO_NAME}/issues/{pr_number}/comments"
    r = SESSION.post(url, json={"body": body}, timeout=30)
    r.raise_for_status()

def parse_tflint_output(text: str) -> Dict[str, List[Dict[str, Any]]]:
    files: Dict[str, List[Dict[str, Any]]] = {}
    for raw in text.splitlines():
        if not raw.strip():
            continue
        low = raw.lower()
        if "issue(s) found" in low or "no issues" in low:
            continue
        m = LINE_RE.match(raw)
        if not m:
            continue
        d = m.groupdict()
        file = d["file"].strip()
        issue = {
            "line": int(d["line"]),
            "col": int(d["col"]),
            "level": d["level"].lower(),
            "rule": (d.get("rule") or "").strip(),
            "msg": (d.get("msg") or "").strip(),
        }
        files.setdefault(file, []).append(issue)
    for file, issues in files.items():
        issues.sort(key=lambda x: (-SEV_WEIGHT.get(x["level"], 0), x["line"], x["col"]))
    return dict(sorted(files.items(), key=lambda kv: kv[0].lower()))

def totals_from_files(files: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
    t = {"error": 0, "warning": 0, "notice": 0, "info": 0}
    for issues in files.values():
        for it in issues:
            lvl = it["level"]
            t[lvl] = t.get(lvl, 0) + 1
    t["info"] = t.get("info", 0) + t.get("notice", 0)
    return {"error": t.get("error", 0), "warning": t.get("warning", 0), "info": t.get("info", 0), "total": sum([t.get("error",0), t.get("warning",0), t.get("info",0)])}

def build_summary_md(totals: Dict[str, int]) -> str:
    return (
        "### 🧹 TFLint Summary\n"
        f"- {SEV_EMOJI['error']} **Errors**: `{totals['error']}`\n"
        f"- {SEV_EMOJI['warning']} **Warnings**: `{totals['warning']}`\n"
        f"- {SEV_EMOJI['info']} **Info**: `{totals['info']}`\n"
        f"- 📦 **Total**: `{totals['total']}`\n\n"
        "_Legend: ❌ error · ⚠️ warning · ℹ️ info_\n\n"
        "✅ **Lint check succeeded**\n"
    )

def build_details_html(files: Dict[str, List[Dict[str, Any]]], workflow_url: str) -> str:
    parts: List[str] = ["<details>", "<summary>📖 Details (Click me)</summary>", ""]
    if not files:
        parts += ["_No issues to display._", "", "</details>", ""]
        return "\n".join(parts)
    MAX_ROWS = 500
    row_count = 0
    truncated = False
    for file_path, issues in files.items():
        parts.append(
            f"\n<details><summary>📄 <code>{escape(file_path)}</code> — <strong>{len(issues)}</strong> issue(s)</summary>\n"
        )
        parts.append(
            "<table>"
            "<thead><tr>"
            "<th align='right'>Line</th>"
            "<th align='right'>Col</th>"
            "<th align='left'>Level</th>"
            "<th align='left'>Rule</th>"
            "<th align='left'>Message</th>"
            "</tr></thead><tbody>"
        )
        for it in issues:
            if row_count >= MAX_ROWS:
                truncated = True
                break
            lvl = it["level"]
            emoji = SEV_EMOJI.get(lvl, "ℹ️")
            rule = escape(it["rule"]) if it["rule"] else ""
            msg = escape(it["msg"])
            if GITHUB_SHA:
                href = f"https://github.com/{REPO_OWNER_FOR_URL}/{REPO_NAME}/blob/{GITHUB_SHA}/{file_path}#L{it['line']}"
                line_cell = f"<a href='{href}'>{it['line']}</a>"
            else:
                line_cell = str(it["line"])
            parts.append(
                "<tr>"
                f"<td align='right'>{line_cell}</td>"
                f"<td align='right'>{it['col']}</td>"
                f"<td>{emoji} <strong>{escape(lvl.title())}</strong></td>"
                f"<td><code>{rule}</code></td>"
                f"<td>{msg}</td>"
                "</tr>"
            )
            row_count += 1
        parts.append("</tbody></table>\n</details>\n")
        if truncated:
            break
    if truncated:
        parts.append(f"<p>⏳ Output truncated to {MAX_ROWS} rows for readability. See full details in the Actions tab: {workflow_url}</p>")
    parts += ["", "</details>", ""]
    return "\n".join(parts)

def footer_md(repo: str, run_id: str) -> str:
    return (
        "\n---\n"
        f"🧑‍💻 **Actor**: @{GITHUB_ACTOR}\n"
        f"⚙️ **Event**: {EVENT_NAME}\n"
        f"📂 **Working Dir**: `{TF_ACTIONS_WORKING_DIR}`\n"
        f"🏗️ **Workflow**: {GITHUB_WORKFLOW}\n"
        f"🔗 **Run Logs**: [View here](https://github.com/{repo}/actions/runs/{run_id})\n"
    )

def main() -> None:
    if EVENT_NAME not in ("pull_request", "pull_request_target"):
        print("::notice::Creation of PR comment was skipped.")
        return
    pr_number = get_pr_number()
    if not pr_number:
        print("::notice::No PR number detected; skipping comment.")
        return
    # Build a clean, deterministic marker that does not inherit other tools' HTML
    wd_visible = TF_ACTIONS_WORKING_DIR or os.environ.get("GITHUB_WORKSPACE", ".")
    hidden_marker = f"<!-- tflint:{wd_visible} -->"
    workflow_url = f"https://github.com/{REPO_OWNER_FOR_URL}/{REPO_NAME}/actions/runs/{RUN_ID}"
    files = parse_tflint_output(TFLINT_OUTPUT or "")
    if PR_DELETE_COMMENT:
        existing_id = find_existing_comment_id(pr_number, wd_visible)
        if existing_id:
            try:
                delete_comment(existing_id)
                print("::notice::Deleted existing TFLint comment.")
            except Exception as e:
                print(f"::warning::Failed deleting TFLint comment: {e}")
        return
    totals = totals_from_files(files)
    # Compose a meaningful header with counts and severity cues
    err = totals.get("error", 0)
    warn = totals.get("warning", 0)
    info = totals.get("info", 0)

    parts = []
    if err:
        parts.append(f"{err} ❌ error{'s' if err != 1 else ''}")
    if warn:
        parts.append(f"{warn} ⚠️ warning{'s' if warn != 1 else ''}")
    if not parts and info:
        parts.append(f"{info} ℹ️ info")

    status = "no issues" if not parts else ", ".join(parts)
    # Final header: tool, status, path
    header_md = f"## 🧹 TFLint for `{wd_visible}` — {status}"
    summary_md = build_summary_md(totals)
    helper_md = (
        "_How to read_: **Errors** block merges, **Warnings** need attention, **Info** is advisory.\n"
        "_Fix locally_: run `tflint --init && tflint` in this folder.\n\n"
        "---\n"
    )
    details_html = build_details_html(files, workflow_url)
    footer = footer_md(REPO, RUN_ID)
    body = (
        f"{header_md}\n\n"
        f"{summary_md}\n{helper_md}"
        f"{details_html}\n"
        f"🔗 [View run logs & artifacts]({workflow_url})\n"
        f"{footer}\n"
        f"{hidden_marker}\n"
    )
    existing_id = find_existing_comment_id(pr_number, wd_visible)
    try:
        if existing_id:
            update_comment(existing_id, body)
            print(f"::notice::Updated TFLint PR comment (id={existing_id}).")
        else:
            create_comment(pr_number, body)
            print("::notice::Created TFLint PR comment.")
    except Exception as e:
        print(f"::error::Failed to upsert TFLint PR comment: {e}")

if __name__ == "__main__":
    main()