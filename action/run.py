#!/usr/bin/env python3
"""
Entry point for the Flaky Scout GitHub Action. Parses a JUnit XML report,
triages every failed test with triage.py, writes a job summary, and
(optionally) posts a PR comment — all via stdlib, no pip install needed.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from parse_junit import extract_failures  # noqa: E402
from triage import triage, to_markdown  # noqa: E402


def post_pr_comment(body: str) -> None:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not (token and repo and event_path):
        return

    event = json.loads(Path(event_path).read_text())
    pr_number = event.get("pull_request", {}).get("number") or event.get("number")
    if not pr_number:
        return  # not a PR context, nothing to comment on

    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    payload = json.dumps({"body": body}).encode()
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=15)
    except urllib.error.URLError as e:
        print(f"::warning::Flaky Scout could not post PR comment: {e}", file=sys.stderr)


def main():
    junit_path = Path(os.environ["FS_JUNIT_XML"])
    post_comment = os.environ.get("FS_POST_COMMENT", "false").lower() == "true"

    if not junit_path.exists():
        print(f"::warning::Flaky Scout: no JUnit XML found at {junit_path}, skipping.")
        return

    failures = extract_failures(junit_path)
    if not failures:
        summary = "### 🔍 Flaky Scout\n\nNo failed tests — nothing to triage.\n"
        _write_summary(summary)
        return

    sections = []
    retry_safe_count = 0
    for f in failures:
        result = triage(f["log"])
        if result.get("retry_safe"):
            retry_safe_count += 1
        heading = f"#### `{f['classname']}.{f['name']}`\n\n" + to_markdown(result, f["log"])
        sections.append(heading)

    header = (
        f"### 🔍 Flaky Scout triage — {len(failures)} failure(s), "
        f"{retry_safe_count} look retry-safe\n\n"
    )
    summary = header + "\n---\n\n".join(sections)

    _write_summary(summary)
    if post_comment:
        post_pr_comment(summary)


def _write_summary(markdown: str) -> None:
    print(markdown)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(markdown + "\n")


if __name__ == "__main__":
    main()
