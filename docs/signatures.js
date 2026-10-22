// Mirrors the SIGNATURES list in ../triage.py — keep these in sync.
// (pattern, category, fixHint) — checked in order, first match wins.
const SIGNATURES = [
  [/NoSuchElementException|ElementNotInteractableException|ElementClickInterceptedException/i,
    "SELECTOR", "Selector likely stale or changed — re-check the locator against current DOM/view."],
  [/StaleElementReferenceException/i,
    "SELECTOR", "Element was re-rendered after lookup — add a re-fetch or explicit wait before interacting."],
  [/TimeoutException|WaitTimeoutError|wait_?for.*timed out|Timed out (waiting|retrying)|Exceeded timeout of \d+\s*ms/i,
    "TIMEOUT", "Increase wait/timeout or check if the awaited condition is reachable at all."],
  [/ConnectionRefusedError|ECONNREFUSED|Connection refused|Failed to establish a new connection/i,
    "ENVIRONMENT", "Target service/emulator/driver wasn't reachable — check it was up before the test ran."],
  [/AssertionError|expect\(.*\)\.to(Equal|Be|Contain|Match|HaveBeenCalled)|assert \S+ ==/i,
    "ASSERTION", "Actual behavior diverged from expected — check if this is a real regression or a stale assertion."],
  [/snapshot (mismatch|does not match)|toMatchSnapshot/i,
    "ASSERTION", "Snapshot is out of date with a real UI change, or the change is unintended — review the diff."],
  [/StaleDriverException|InvalidSessionIdException|session (not found|deleted)/i,
    "ENVIRONMENT", "Driver/session died mid-test — check device/emulator stability and session timeouts."],
  [/retry|flak(y|iness)|passed on (the )?previous \d+ runs|intermittent/i,
    "FLAKY", "Failure pattern suggests timing/flakiness rather than a real defect — consider quarantine + retry."],
];

function signatureMatch(log) {
  for (const [pattern, category, fixHint] of SIGNATURES) {
    if (pattern.test(log)) {
      return { category, rootCause: `Matched known signature: ${pattern.source.split("|")[0]}`, fixHint, retrySafe: category === "FLAKY" };
    }
  }
  return null;
}
