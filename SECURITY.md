# Security

Flaky Scout's core privacy claim — failure logs never leave the runner — is
about where *data* goes. It says nothing by itself about whether it's safe
to run on *untrusted input*. This doc covers the second part: what's
actually hardened in the code, and what remains a trust decision you make
when you wire this into a workflow.

## Threat model

The input to this tool (a JUnit XML test report) is **test output** — which
means its content is influenced by whatever the test subject did. On a
workflow triggered by `pull_request`, that means a pull request (potentially
from a fork, depending on your repo's settings) can influence:

- test names, class names, failure messages, and stack trace text
- indirectly, what the local model is asked to summarize, and therefore
  what text comes back as `root_cause` / `fix_hint`

Treat all of that as **attacker-influenced**, not trusted, even though it's
"just test output."

## What's mitigated in code

- **XML entity-expansion / XXE** ([`parse_junit.py`](action/parse_junit.py)) —
  a JUnit report never legitimately needs a `<!DOCTYPE`/`<!ENTITY>`
  declaration. Rather than hand-roll `expat` hardening (easy to get subtly
  wrong), any report containing one is refused outright — that's the only
  mechanism billion-laughs and XXE attacks have, so refusing it removes the
  attack class without adding a dependency.
- **Oversized input / resource exhaustion** — JUnit XML is capped at 20MB,
  CLI/stdin log input is read with a bounded read (not read-then-truncate)
  at 200KB, and processing stops after 200 failed testcases in one report.
- **Markdown/HTML injection into PR comments** ([`triage.py`](triage.py)'s
  `_md_escape`) — `root_cause`/`fix_hint` can originate from the model,
  which read attacker-influenced log text. Without escaping, a crafted
  failure log could make the model emit a Markdown link/image (phishing,
  tracking pixel) or break out of a code span, posted to the PR under the
  workflow's own token. Link/image syntax, backticks, and angle brackets are
  escaped before rendering; test names (also XML-sourced) are escaped too.
  Our own hardcoded signature strings are left unescaped since they're
  trusted and escaping them just hurts readability for no benefit.
- **Malformed/untyped model output** — the model's JSON response is
  validated, not trusted blindly: `category` must be one of the fixed enum
  values, `retry_safe` must literally be the JSON boolean `true` (not a
  truthy string), and `root_cause`/`fix_hint` are length-capped.
- **Unbounded `kb.json` growth** — capped at 5,000 entries, oldest evicted
  first, so a long-lived runner's cache can't grow forever.
- **PR comment body size** — capped below GitHub's 65536-char API limit.
- **Script injection via workflow inputs** — not a new fix, but worth
  stating: [`action.yml`](action.yml) passes every input through an `env:`
  block, never interpolates `${{ inputs.* }}` directly into a `run:` shell
  script. That's what avoids the classic GitHub Actions vulnerability where
  an attacker-controlled input (e.g. a PR title) containing `$(...)` or
  backticks gets executed as shell when interpolated directly into a script.

## What's a trust decision, not a bug

**Self-hosted runners executing code influenced by a pull request** is the
big one, and it's not something this tool can fix — it's inherent to the
"local model" design (Ollama has to run *somewhere*, and that somewhere has
to be a runner you control). If your workflow also checks out and *runs* PR
code (tests have to run, after all) on that same self-hosted runner,
whoever can open a PR can run code on your infrastructure. That's true with
or without Flaky Scout in the workflow.

Mitigate this the standard GitHub Actions ways, not through this tool:

- Require approval for first-time/outside contributors before workflows run
  on PRs (repo Settings → Actions → "Fork pull request workflows").
- Prefer ephemeral, single-use self-hosted runners (e.g. via Actions Runner
  Controller) over long-lived ones, so compromise doesn't persist.
- Never use `pull_request_target` with a step that checks out and executes
  PR code — see the warning in
  [`example-usage.yml`](.github/workflows/example-usage.yml).
- Keep the `permissions:` block scoped to exactly what's needed
  (`contents: read`, `pull-requests: write` — see the example workflow).
- If your repo doesn't accept external PRs, most of this is moot — the
  trust boundary only matters once untrusted contributors can open one.

**`kb.json` as a shared cache across runs** — a persistent self-hosted
runner's cache is written to by every job that runs on it. A sufficiently
motivated attacker-influenced PR could, in principle, try to seed a
misleading cache entry for a failure signature your real code later
produces. The entry cap limits the blast radius but doesn't eliminate this;
treat `retry_safe: true` as a hint for a human, not an instruction to
auto-retry unattended in a high-stakes pipeline.

## Reporting a vulnerability

Open a GitHub issue, or email sandeepsai1234.ss@gmail.com for anything
you'd rather not post publicly first.
