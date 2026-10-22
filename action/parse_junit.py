"""Extract failed/errored test cases from a JUnit XML report.

Works with the JUnit XML dialect produced by pytest, Jest (jest-junit),
TestNG/Selenium, and most CI test runners — they all agree on the
<testcase><failure|error>...</failure></testcase> shape even when the
surrounding <testsuite(s)> wrapper differs slightly.
"""
import xml.etree.ElementTree as ET
from pathlib import Path


def extract_failures(junit_xml_path: Path) -> list[dict]:
    tree = ET.parse(junit_xml_path)
    root = tree.getroot()

    testcases = root.iter("testcase")
    failures = []
    for tc in testcases:
        problem = tc.find("failure")
        if problem is None:
            problem = tc.find("error")
        if problem is None:
            continue

        name = tc.get("name", "unknown test")
        classname = tc.get("classname", "")
        message = problem.get("message", "")
        text = (problem.text or "").strip()

        log = f"Test: {classname}.{name}\n{message}\n{text}".strip()
        failures.append({"name": name, "classname": classname, "log": log})

    return failures
