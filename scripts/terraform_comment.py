#!/usr/bin/env python3
import json, os
from pathlib import Path
from typing import Optional, List
import requests

# ---- Env / setup
GITHUB_API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
REPO = os.environ["GITHUB_REPOSITORY"]
OWNER, REPO_NAME = REPO.split("/", 1)
TOKEN = os.environ.get("GITHUB_TOKEN", "")
EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME", "")
EVENT_PATH = os.environ.get("GITHUB_EVENT_PATH", "")
RUN_ID = os.environ.get("GITHUB_RUN_ID", "")
REPO_OWNER_FOR_URL = os.environ.get("GITHUB_REPOSITORY_OWNER", OWNER)
GITHUB_ACTOR = os.environ.get("GITHUB_ACTOR", "")
GITHUB_WORKFLOW = os.environ.get("GITHUB_WORKFLOW", "")
TF_ACTIONS_WORKING_DIR = (os.environ.get("TF_ACTIONS_WORKING_DIR", ".") or ".").strip()
PR_COMMENT_MARKER = (os.environ.get("PR_COMMENT_MARKER", "") or "").strip()
CREATE_COMMENT = os.environ.get("CREATE_COMMENT", "false").lower() == "true"
GITHUB_SHA = os.environ.get("GITHUB_SHA", "")

# Counts exported by action step
TF_ADD_COUNT = os.environ.get("TF_ADD_COUNT", "0")
TF_CHANGE_COUNT = os.environ.get("TF_CHANGE_COUNT", "0")
TF_DESTROY_COUNT = os.environ.get("TF_DESTROY_COUNT", "0")

SESSION = requests.Session()
SESSION.headers.update({
  "Accept": "application/vnd.github+json",
  "Authorization": f"Bearer {TOKEN}" if TOKEN else "",
  "X-GitHub-Api-Version": "2022-11-28",
  "User-Agent": "terraform-plan-pr-comment/py",
})

def get_pr_number() -> Optional[int]:
    # Primary: read PR number from the event payload (works for pull_request events)
    if EVENT_PATH and Path(EVENT_PATH).is_file():
        try:
            with open(EVENT_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if "pull_request" in payload and "number" in payload:
                return int(payload["number"])
            # Some events nest differently; try common locations
            if "issue" in payload and "pull_request" in payload.get("issue", {}):
                return int(payload["issue"].get("number"))
        except Exception as e:
            print(f"::warning::Failed reading event payload for PR number: {e}")
    # Fallback: query PRs associated with this commit SHA
    if GITHUB_SHA:
        try:
            url = f"{GITHUB_API}/repos/{OWNER}/{REPO_NAME}/commits/{GITHUB_SHA}/pulls"
            r = SESSION.get(
                url,
                headers={"Accept": "application/vnd.github.groot-preview+json"},
                timeout=30,
            )
            r.raise_for_status()
            prs = r.json()
            if isinstance(prs, list) and prs:
                return int(prs[0].get("number"))
        except Exception as e:
            print(f"::warning::Failed resolving PR via commit association: {e}")
    return None

def list_all_comments(pr_number: int) -> List[dict]:
    comments, page = [], 1
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

def find_existing_comment_id(pr_number: int, marker_html: str) -> Optional[int]:
    for c in list_all_comments(pr_number):
        body = (c.get("body") or "")
        if marker_html in body:
            return c["id"]
    return None

def update_comment(comment_id: int, body: str) -> None:
    url = f"{GITHUB_API}/repos/{OWNER}/{REPO_NAME}/issues/comments/{comment_id}"
    r = SESSION.patch(url, json={"body": body}, timeout=30)
    r.raise_for_status()

def create_comment(pr_number: int, body: str) -> None:
    url = f"{GITHUB_API}/repos/{OWNER}/{REPO_NAME}/issues/{pr_number}/comments"
    r = SESSION.post(url, json={"body": body}, timeout=30)
    r.raise_for_status()

def workflow_url() -> str:
    return f"https://github.com/{REPO_OWNER_FOR_URL}/{REPO_NAME}/actions/runs/{RUN_ID}"

def footer_md() -> str:
    run_url = workflow_url()
    lines = [
        "\n---\n",
        f"🧑‍💻 **Actor**: @{GITHUB_ACTOR}\n",
        f"📂 **Dir**: `{TF_ACTIONS_WORKING_DIR}`\n",
        f"🔗 **Run**: [logs]({run_url})\n",
    ]
    if GITHUB_SHA:
        commit_url = f"{os.environ.get('GITHUB_SERVER_URL','https://github.com')}/{REPO_OWNER_FOR_URL}/{REPO_NAME}/commit/{GITHUB_SHA}"
        short = GITHUB_SHA[:7]
        lines.append(f"🔧 **Commit**: [{short}]({commit_url})\n")
    return "".join(lines)

def build_summary_md() -> str:
    return (
        "### 🚀 Terraform Plan Summary\n"
        f"- ➕ (+) **Add**: `{TF_ADD_COUNT}`\n"
        f"- ♻️ (~) **Change**: `{TF_CHANGE_COUNT}`\n"
        f"- 🗑️ (-) **Destroy**: `{TF_DESTROY_COUNT}`\n\n"
        "✅ **Plan succeeded**\n"
    )


def _extract_plan_only(text: str) -> str:
    # Keep only the plan body, drop any init noise if present
    lines = text.splitlines()
    start = 0
    for i, l in enumerate(lines):
        if "Terraform used the selected providers to generate the following execution" in l:
            start = i
            break
    return "\n".join(lines[start:]).strip()

def read_plan_details(footer: str = "") -> str:
    # Prefer the human-readable show output we write explicitly
    plan_txt = Path(TF_ACTIONS_WORKING_DIR) / "plan.txt"
    if plan_txt.exists():
        text = plan_txt.read_text(encoding="utf-8", errors="replace")
        body = _extract_plan_only(text)
        return (
            "<details>\n"
            "<summary>📖 Details (Click me)</summary>\n\n"
            "```terraform\n" + body + "\n``""\n\n"
            f"{footer}"
            "</details>\n"
        )
    # Fallback: old behavior using output.txt (may contain init noise)
    out_txt = Path("output.txt")
    if out_txt.exists():
        text = out_txt.read_text(encoding="utf-8", errors="replace")
        body = _extract_plan_only(text)
        return (
            "<details>\n"
            "<summary>📖 Details (Click me)</summary>\n\n"
            "```terraform\n" + body + "\n``""\n\n"
            f"{footer}"
            "</details>\n"
        )
    return (
        "<details>\n<summary>📖 Details (Click me)</summary>\n\n"
        "_Not available._\n\n"
        f"{footer}"
        "</details>\n"
    )

def main() -> None:
    # Only PRs
    if EVENT_NAME not in ("pull_request", "pull_request_target"):
        print("::notice::Creation of PR comment was skipped (not a PR event).")
        return
    pr_number = get_pr_number()
    if not pr_number:
        print("::notice::No PR number detected; skipping comment.")
        return
    if CREATE_COMMENT and not TOKEN:
        print("::error::GITHUB_TOKEN is not set but CREATE_COMMENT=true; cannot post PR comment.")
        return

    # Marker: honor provided HTML comment, else synthesize from working dir
    if PR_COMMENT_MARKER.startswith("<!--") and PR_COMMENT_MARKER.endswith("-->"):
        marker_html = PR_COMMENT_MARKER
    else:
        marker_html = f"<!-- tf-plan:{TF_ACTIONS_WORKING_DIR} -->"

    header = f"## 📦 Terraform Plan for `{TF_ACTIONS_WORKING_DIR}` {marker_html}"
    summary = build_summary_md()
    footer = footer_md()
    details_html = read_plan_details(footer)
    # `details_html` now includes the footer, so do not append it again
    body = f"{header}\n\n{summary}\n{details_html}\n{marker_html}\n"

    print(f"::notice::Upserting Terraform plan PR comment for {TF_ACTIONS_WORKING_DIR} with marker {marker_html}")
    existing_id = find_existing_comment_id(pr_number, marker_html)
    try:
        if existing_id:
            update_comment(existing_id, body)
            print(f"::notice::Updated Terraform plan PR comment (id={existing_id}).")
        else:
            create_comment(pr_number, body)
            print("::notice::Created Terraform plan PR comment.")
    except Exception as e:
        print(f"::error::Failed to upsert Terraform plan PR comment: {e}")

if __name__ == "__main__":
    main()