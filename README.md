# 🔍 Flaky Scout

**CI test-failure triage that never sends your logs anywhere.**

🌐 **[Live site + interactive demo](https://sandy-262.github.io/flaky-scout/)** — try the classifier in your browser before installing anything.

Every time a test fails in CI, something has to look at the stack trace and
figure out: is this a real bug, a stale selector, a timing-flaky test, or an
infra hiccup? Usually that's an engineer, manually, repeatedly, for the same
handful of failure shapes. Flaky Scout automates the first pass — and because
it runs entirely on your own runner against a local 8B model, your test logs
and stack traces (which can contain real user data, API responses, internal
URLs) never leave your infrastructure and never hit a third-party API.

```
### 🔍 Flaky Scout triage — 2 failure(s), 1 look retry-safe

#### `tests.test_login.test_submit_button_visible`
### 🎯 Flaky Scout triage: `SELECTOR`
**Root cause:** Matched known signature: NoSuchElementException
**Suggested fix:** Selector likely stale or changed — re-check the locator against current DOM/view.
**Auto-retry:** no — needs a look
```

## Why local-first, not another API wrapper

Most "AI test triage" tools are a thin prompt wrapper around a hosted LLM API,
which means every failing test's logs — including whatever request/response
data, user info, or internal hostnames happened to be captured in that
failure — get shipped to a third party. For a lot of QA/enterprise teams
that's a hard no, regardless of how good the triage is.

Flaky Scout runs against [Ollama](https://ollama.com) on your own
self-hosted runner. Nothing is sent off the box. No API key, no per-call
cost, no data-retention question to answer for security review.

That said, a self-hosted runner executing code influenced by a pull request
is its own trust decision, independent of this tool — see
[SECURITY.md](SECURITY.md) for the threat model, what's hardened in the
code (input size limits, XML entity-expansion/XXE protection, Markdown
injection escaping on anything model-derived), and how to configure the
trigger/permissions safely.

## How it classifies failures

Cost-layered, so the model is only invoked when it's actually needed:

1. **Signature match** (instant, free) — regexes for the common, well-known
   failure shapes: `NoSuchElementException`, `TimeoutException`,
   `ConnectionRefusedError`, assertion failures, snapshot mismatches, etc.
2. **Knowledge-base lookup** (instant, free) — a novel failure the model has
   classified before gets cached (by a normalized hash of the log, so line
   numbers/timestamps don't matter) and matched instantly next time.
3. **Local model** (a few seconds, still free) — only genuinely new failure
   patterns reach `qwen3:8b` via Ollama, which returns a category, root
   cause, fix hint, and whether the failure looks safe to auto-retry. The
   result gets saved back into the knowledge base for step 2 next time.

## Quick start

Requires a **self-hosted runner** with [Ollama](https://ollama.com) installed
and a model pulled (`ollama pull qwen3:8b`) — this is the trade-off for
"nothing leaves the box": you need infra that can run the model.

See [`.github/workflows/example-usage.yml`](.github/workflows/example-usage.yml)
for the full version with `permissions:` scoping and security notes — short
version:

```yaml
# .github/workflows/test.yml
permissions:
  contents: read
  pull-requests: write
jobs:
  test:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
      - run: pytest --junitxml=report.xml
        continue-on-error: true
      - uses: Sandy-262/flaky-scout@7456a8e226a738c86b8ea805fb1ac6eaed27be01 # v1.0.0
        with:
          junit-xml: report.xml
          post-comment: true
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

Works with any test runner that can emit JUnit XML — pytest, Jest
(`jest-junit`), TestNG/Selenium, Appium test suites, etc.

## Command-line use (outside CI)

```bash
python3 triage.py --log path/to/failure.log
cat failure.log | python3 triage.py --format markdown
```

No dependencies beyond Python 3's standard library and a running
`ollama serve`.

## Project layout

- [`triage.py`](triage.py) — the classifier: signatures → KB → local model.
- [`action.yml`](action.yml) + [`action/`](action) — the GitHub Action
  wrapper: parses JUnit XML, triages each failure, writes a job summary,
  optionally posts a PR comment.
- [`fixtures/`](fixtures) — sample failure logs/reports across frameworks,
  used to sanity-check classification quality.

## Status / roadmap

This is a working first version, built to be genuinely useful for a small
team as-is. Ideas for where it could go next: a hosted dashboard aggregating
triage trends across repos, Slack/Teams notifications, support for
non-self-hosted runners via a lightweight relay. Issues and PRs welcome.
