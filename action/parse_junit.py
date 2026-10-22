"""Extract failed/errored test cases from a JUnit XML report.

Works with the JUnit XML dialect produced by pytest, Jest (jest-junit),
TestNG/Selenium, and most CI test runners — they all agree on the
<testcase><failure|error>...</failure></testcase> shape even when the
surrounding <testsuite(s)> wrapper differs slightly.

This file is a CI-trust-boundary: the XML it parses is test *output*,
which is influenced by whatever the test subject under CI did — on a
fork-PR-triggered workflow that's attacker-influenced input, not just
your own team's data. See hardening notes inline and SECURITY.md.
"""
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_XML_BYTES = 20_000_000   # 20MB of JUnit XML is already an enormous report
MAX_FAILURES = 200           # bound how many testcases we'll ever process/render
MAX_FIELD_CHARS = 4_000      # per-field cap before this even reaches triage.py


class UnsafeReportError(ValueError):
    """Raised when a JUnit XML report looks unsafe to parse, not just malformed."""


def extract_failures(junit_xml_path: Path) -> list[dict]:
    raw = junit_xml_path.read_bytes()

    if len(raw) > MAX_XML_BYTES:
        raise UnsafeReportError(
            f"{junit_xml_path} is {len(raw)} bytes, over the {MAX_XML_BYTES}-byte "
            "limit — refusing to parse (either a broken report generator, or an "
            "attempt to exhaust memory/CPU on the runner)."
        )

    # A legitimate JUnit XML report never needs a DOCTYPE/custom ENTITY
    # declaration. That's also the only way to mount a billion-laughs
    # (entity-expansion DoS) or classic XXE (external entity / file-read)
    # attack through this parser. Rather than hand-roll expat hardening
    # (easy to get subtly wrong), we just refuse any report that has one —
    # a cheap, dependency-free check that removes the attack class entirely.
    head = raw[:2048].lower()
    if b"<!doctype" in head or b"<!entity" in head:
        raise UnsafeReportError(
            f"{junit_xml_path} contains a DOCTYPE/ENTITY declaration, which a "
            "JUnit report should never need — refusing to parse (this is the "
            "mechanism XML entity-expansion and XXE attacks require)."
        )

    tree = ET.fromstring(raw)
    testcases = tree.iter("testcase")

    failures = []
    for tc in testcases:
        if len(failures) >= MAX_FAILURES:
            break

        problem = tc.find("failure")
        if problem is None:
            problem = tc.find("error")
        if problem is None:
            continue

        name = (tc.get("name") or "unknown test")[:MAX_FIELD_CHARS]
        classname = (tc.get("classname") or "")[:MAX_FIELD_CHARS]
        message = (problem.get("message") or "")[:MAX_FIELD_CHARS]
        text = (problem.text or "").strip()[:MAX_FIELD_CHARS]

        log = f"Test: {classname}.{name}\n{message}\n{text}".strip()
        failures.append({"name": name, "classname": classname, "log": log})

    return failures
