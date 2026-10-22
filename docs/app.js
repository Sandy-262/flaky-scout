const EXAMPLES = {
  selector: `org.openqa.selenium.NoSuchElementException: Unable to locate element: {"method":"css selector","selector":"#submit-btn"}
  at org.openqa.selenium.remote.RemoteWebDriver$RemoteWebDriverElementFinder.findElement(RemoteWebDriver.java:420)
  at com.example.tests.CheckoutTest.testSubmitOrder(CheckoutTest.java:48)`,
  environment: `ConnectionRefusedError: [Errno 61] Connection refused
  at Object.connect (appium-driver.js:112)
  at TestSetup.beforeEach (login.spec.js:8)
Test: 'should load the login screen'
This test passed on the previous 14 runs.`,
  novel: `Expected cart badge to read "2" within 300ms of the second add-to-cart
click, but it read "1" at the 300ms mark and only updated to "2" after
roughly 900ms. The badge count is driven by a Redux selector that
recomputes on a debounced store subscription (120ms debounce), and the
test's second click fires only 150ms after the first.

Passed 41/50 times locally with --repeat, failed 9/50.`,
};

const CATEGORY_META = {
  TIMEOUT: { emoji: "⏱️", label: "Timeout" },
  SELECTOR: { emoji: "🎯", label: "Selector" },
  ASSERTION: { emoji: "❌", label: "Assertion" },
  ENVIRONMENT: { emoji: "🌐", label: "Environment" },
  FLAKY: { emoji: "🔁", label: "Flaky" },
  UNKNOWN: { emoji: "❓", label: "Unknown" },
};

const input = document.getElementById("log-input");
const resultEl = document.getElementById("result");
const runBtn = document.getElementById("run-btn");

function renderResult(result) {
  if (!result) {
    const meta = CATEGORY_META.UNKNOWN;
    resultEl.innerHTML = `
      <div class="result-card result-unknown">
        <div class="result-head">${meta.emoji} <strong>That's new — time to call in the AI</strong></div>
        <p>This is exactly where your own private AI takes over. In the real tool, this log would go to
        your own <code>qwen3:8b</code> model via Ollama — running on your hardware, never a cloud API —
        which reads the full description and comes back with a cause, a fix, and a verdict.</p>
        <p>This web page is just a static demo with no server behind it, so it can only show you the
        free instant-recognition layer. Install the real thing to see the AI layer in action.</p>
      </div>`;
    return;
  }
  const meta = CATEGORY_META[result.category] || CATEGORY_META.UNKNOWN;
  const retry = result.retrySafe ? "Yes — likely safe to auto-retry" : "No — needs a look";
  resultEl.innerHTML = `
    <div class="result-card result-${result.category.toLowerCase()}">
      <div class="result-head">${meta.emoji} <strong>${meta.label}</strong></div>
      <dl>
        <dt>Root cause</dt><dd>${result.rootCause}</dd>
        <dt>Suggested fix</dt><dd>${result.fixHint}</dd>
        <dt>Auto-retry</dt><dd>${retry}</dd>
      </dl>
      <p class="source-note">matched instantly, client-side, no server involved</p>
    </div>`;
}

function run() {
  const log = input.value.trim();
  if (!log) {
    resultEl.innerHTML = `<p class="hint">Paste a failure log above, or click one of the examples.</p>`;
    return;
  }
  renderResult(signatureMatch(log));
}

runBtn.addEventListener("click", run);

document.querySelectorAll("[data-example]").forEach((btn) => {
  btn.addEventListener("click", () => {
    input.value = EXAMPLES[btn.dataset.example];
    run();
  });
});
