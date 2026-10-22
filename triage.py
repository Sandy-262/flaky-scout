#!/usr/bin/env python3
"""
Flaky Scout — CI test-failure triage, local-first.

Classifies a test failure log into a category (signature match first,
local Ollama model only for patterns it hasn't seen before), and says
whether it looks safe to auto-retry. Nothing leaves the machine it runs on.

Usage:
    python3 triage.py --log path/to/failure.log
    cat failure.log | python3 triage.py
    python3 triage.py --log failure.log --format markdown
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA_URL = os.environ.get("FS_OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.environ.get("FS_MODEL", "qwen3:8b")
KB_PATH = Path(__file__).parent / "kb.json"

CATEGORIES = ["TIMEOUT", "SELECTOR", "ASSERTION", "ENVIRONMENT", "FLAKY", "UNKNOWN"]

# Fast path: common failure signatures across Selenium/Appium/pytest/Jest/JUnit.
# (pattern, category, fix_hint) — checked in order, first match wins.
SIGNATURES = [
    (r"NoSuchElementException|ElementNotInteractableException|ElementClickInterceptedException",
     "SELECTOR", "Selector likely stale or changed — re-check the locator against current DOM/view."),
    (r"StaleElementReferenceException",
     "SELECTOR", "Element was re-rendered after lookup — add a re-fetch or explicit wait before interacting."),
    (r"TimeoutException|WaitTimeoutError|wait_?for.*timed out|Timed out (waiting|retrying)|Exceeded timeout of \d+\s*ms",
     "TIMEOUT", "Increase wait/timeout or check if the awaited condition is reachable at all."),
    (r"ConnectionRefusedError|ECONNREFUSED|Connection refused|Failed to establish a new connection",
     "ENVIRONMENT", "Target service/emulator/driver wasn't reachable — check it was up before the test ran."),
    (r"AssertionError|expect\(.*\)\.to(Equal|Be|Contain|Match|HaveBeenCalled)|assert \S+ ==",
     "ASSERTION", "Actual behavior diverged from expected — check if this is a real regression or a stale assertion."),
    (r"snapshot (mismatch|does not match)|toMatchSnapshot",
     "ASSERTION", "Snapshot is out of date with a real UI change, or the change is unintended — review the diff."),
    (r"StaleDriverException|InvalidSessionIdException|session (not found|deleted)",
     "ENVIRONMENT", "Driver/session died mid-test — check device/emulator stability and session timeouts."),
    (r"retry|flak(y|iness)|passed on (the )?previous \d+ runs|intermittent",
     "FLAKY", "Failure pattern suggests timing/flakiness rather than a real defect — consider quarantine + retry."),
]


def load_kb() -> dict:
    if KB_PATH.exists():
        return json.loads(KB_PATH.read_text())
    return {}


def save_kb(kb: dict) -> None:
    KB_PATH.write_text(json.dumps(kb, indent=2, sort_keys=True) + "\n")


def signature_match(log: str):
    for pattern, category, fix_hint in SIGNATURES:
        if re.search(pattern, log, re.IGNORECASE):
            return {
                "category": category,
                "root_cause": f"Matched known signature: {pattern.split('|')[0]}",
                "fix_hint": fix_hint,
                "retry_safe": category == "FLAKY",
                "source": "signature",
            }
    return None


def kb_match(log: str, kb: dict):
    key = hashlib.sha256(_normalize(log).encode()).hexdigest()[:16]
    entry = kb.get(key)
    if entry:
        result = dict(entry)
        result["source"] = "kb"
        return result
    return None


def _normalize(log: str) -> str:
    # Strip volatile bits (line numbers, timestamps, hex ids) so repeated
    # occurrences of "the same" failure hash the same.
    log = re.sub(r"0x[0-9a-fA-F]+", "0xHEX", log)
    log = re.sub(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\S*", "TIMESTAMP", log)
    log = re.sub(r":\d+:\d+|:\d+\)", ":N:N", log)
    log = re.sub(r"\s+", " ", log).strip()
    return log[:2000]


def model_classify(log: str):
    prompt = (
        "You are a CI test-failure triage assistant. Given a test failure log, "
        "respond with ONLY a JSON object (no other text) with these fields: "
        "category (one of TIMEOUT, SELECTOR, ASSERTION, ENVIRONMENT, FLAKY, UNKNOWN), "
        "root_cause (one sentence), fix_hint (one sentence), "
        "retry_safe (true/false boolean - true if this looks like a transient/flaky "
        "failure safe to auto-retry).\n\nFailure log:\n" + log[:4000]
    )
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": "json",
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError) as e:
        return {
            "category": "UNKNOWN",
            "root_cause": f"Local model unreachable ({e}) — is `ollama serve` running?",
            "fix_hint": "Start Ollama and re-run, or inspect the log manually.",
            "retry_safe": False,
            "source": "error",
        }

    raw = body.get("response", "{}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"category": "UNKNOWN", "root_cause": "Model returned unparseable output.",
                   "fix_hint": "Inspect the log manually.", "retry_safe": False}

    if parsed.get("category") not in CATEGORIES:
        parsed["category"] = "UNKNOWN"
    parsed["source"] = "model"
    return parsed


def triage(log: str, use_kb: bool = True) -> dict:
    result = signature_match(log)
    if result:
        return result

    kb = load_kb() if use_kb else {}
    if use_kb:
        result = kb_match(log, kb)
        if result:
            return result

    result = model_classify(log)

    if use_kb and result.get("source") == "model" and result["category"] != "UNKNOWN":
        key = hashlib.sha256(_normalize(log).encode()).hexdigest()[:16]
        kb[key] = {k: v for k, v in result.items() if k != "source"}
        save_kb(kb)

    return result


def to_markdown(result: dict, log: str) -> str:
    emoji = {"TIMEOUT": "⏱️", "SELECTOR": "🎯", "ASSERTION": "❌", "ENVIRONMENT": "🌐",
             "FLAKY": "🔁", "UNKNOWN": "❓"}.get(result["category"], "❓")
    retry = "yes, likely safe to auto-retry" if result.get("retry_safe") else "no — needs a look"
    source_note = {"signature": "matched a known pattern instantly",
                   "kb": "matched a pattern seen before (cached from a prior local-model call)",
                   "model": "classified by the local model (new pattern)",
                   "error": "could not classify"}.get(result.get("source"), "")
    return (
        f"### {emoji} Flaky Scout triage: `{result['category']}`\n\n"
        f"**Root cause:** {result['root_cause']}\n\n"
        f"**Suggested fix:** {result['fix_hint']}\n\n"
        f"**Auto-retry:** {retry}\n\n"
        f"<sub>{source_note} · classified locally, nothing sent off-box</sub>\n"
    )


def main():
    ap = argparse.ArgumentParser(description="Triage a CI test failure log, locally.")
    ap.add_argument("--log", type=Path, help="Path to the failure log. Omit to read stdin.")
    ap.add_argument("--format", choices=["json", "markdown"], default="json")
    ap.add_argument("--no-kb", action="store_true", help="Skip the knowledge-base cache.")
    args = ap.parse_args()

    log_text = args.log.read_text() if args.log else sys.stdin.read()
    if not log_text.strip():
        print("No log content given.", file=sys.stderr)
        sys.exit(1)

    result = triage(log_text, use_kb=not args.no_kb)

    if args.format == "markdown":
        print(to_markdown(result, log_text))
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
