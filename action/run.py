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
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from parse_junit import extract_failures, UnsafeReportError  # noqa: E402
from triage import triage, to_markdown, _md_escape  # noqa: E402

MAX_COMMENT_CHARS = 60_000  # GitHub caps issue/PR comment bodies at 65536


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

    try:
        failures = extract_failures(junit_path)
    except UnsafeReportError as e:
        # Fail closed and loud: this means the report was refused for a
        # safety reason (oversized, or carries a DOCTYPE/ENTITY), not just
        # malformed. Don't silently continue past that.
        print(f"::error::Flaky Scout refused to parse {junit_path}: {e}")
        sys.exit(1)
    except ET.ParseError as e:
        print(f"::warning::Flaky Scout: {junit_path} isn't valid XML ({e}), skipping.")
        return

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
        # classname/name come from the XML (test output) too — same
        # untrusted-input rule applies, and they sit inside a backtick
        # code span here so an unescaped backtick could break out of it.
        safe_id = _md_escape(f"{f['classname']}.{f['name']}")
        heading = f"#### `{safe_id}`\n\n" + to_markdown(result, f["log"])
        sections.append(heading)

    header = (
        f"### 🔍 Flaky Scout triage — {len(failures)} failure(s), "
        f"{retry_safe_count} look retry-safe\n\n"
    )
    summary = header + "\n---\n\n".join(sections)
    if len(summary) > MAX_COMMENT_CHARS:
        summary = summary[:MAX_COMMENT_CHARS] + "\n\n…(truncated, too many/large failures to show in full)\n"

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
