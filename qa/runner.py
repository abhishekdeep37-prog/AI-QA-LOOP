"""Run scenarios against a live app with Playwright and return structured results.

API steps use Playwright's APIRequestContext (no browser needed). UI steps use
Chromium and are skipped if the suite is run with ui=False.

Each result carries enough evidence for the triage agent: the failing step,
what was expected, what actually came back, and whether a rerun passed
(a rerun that passes means the failure is classified as flaky, not a bug).
"""
import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright

UI_TIMEOUT_MS = 3000


class StepFailure(Exception):
    def __init__(self, kind, expected, actual, detail=""):
        super().__init__(detail or f"expected {expected!r}, got {actual!r}")
        self.kind, self.expected, self.actual, self.detail = kind, expected, actual, detail


def _values_equal(expected, actual):
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(expected - actual) < 0.005
    return expected == actual


def _run_api_step(api, step):
    method = step["method"].upper()
    kwargs = {"data": step["json"]} if "json" in step else {}
    resp = api.fetch(step["path"], method=method, **kwargs)
    try:
        body = resp.json()
    except Exception:
        body = resp.text()[:300]
    want_status = step.get("expect_status", 200)
    if resp.status != want_status:
        raise StepFailure("status", want_status, resp.status, f"response body: {body}")
    for key, want in step.get("expect_json", {}).items():
        got = body.get(key, "<missing>") if isinstance(body, dict) else "<non-json body>"
        if got == "<missing>" or got == "<non-json body>" or not _values_equal(want, got):
            raise StepFailure("json_field", {key: want}, {key: got}, f"response body: {body}")


def _run_ui_step(page, base_url, step):
    action = step["action"]
    if action == "goto":
        page.goto(base_url + step["value"])
    elif action == "fill":
        page.fill(step["selector"], str(step["value"]), timeout=UI_TIMEOUT_MS)
    elif action == "click":
        page.click(step["selector"], timeout=UI_TIMEOUT_MS)
    elif action == "expect_text":
        try:
            expect(page.locator(step["selector"])).to_contain_text(str(step["value"]), timeout=UI_TIMEOUT_MS)
        except AssertionError:
            actual = "<not found>"
            try:
                actual = page.locator(step["selector"]).inner_text(timeout=500)
            except PlaywrightError:
                pass
            raise StepFailure("ui_text", step["value"], actual)


def _has_ui(scenario):
    return any(s.get("type") == "ui" for s in scenario["steps"])


def _execute(scenario, base_url, api, browser):
    """Run one scenario once. Returns a result dict."""
    started = time.time()
    result = {"id": scenario["id"], "requirement_id": scenario["requirement_id"], "title": scenario["title"]}
    api.post("/api/reset")
    page = browser.new_page() if browser and _has_ui(scenario) else None
    step_index = 0
    try:
        for step_index, step in enumerate(scenario["steps"]):
            if step["type"] == "api":
                _run_api_step(api, step)
            else:
                _run_ui_step(page, base_url, step)
        result["status"] = "passed"
    except StepFailure as f:
        result.update(status="failed", failed_step_index=step_index, failed_step=scenario["steps"][step_index],
                      error_kind=f.kind, expected=f.expected, actual=f.actual, detail=f.detail)
    except PlaywrightError as e:
        result.update(status="failed", failed_step_index=step_index, failed_step=scenario["steps"][step_index],
                      error_kind="exception", expected=None, actual=None, detail=str(e).splitlines()[0][:300])
    finally:
        if page:
            page.close()
    result["duration_ms"] = int((time.time() - started) * 1000)
    return result


def run_scenarios(scenarios, base_url, ui=True, headless=True, retries=1):
    """Run every scenario. Failures are retried `retries` times; a pass on retry is reported as "flaky"."""
    results = []
    with sync_playwright() as p:
        api = p.request.new_context(base_url=base_url)
        browser = p.chromium.launch(headless=headless) if ui and any(_has_ui(s) for s in scenarios) else None
        try:
            for scenario in scenarios:
                if _has_ui(scenario) and browser is None:
                    results.append({"id": scenario["id"], "requirement_id": scenario["requirement_id"],
                                    "title": scenario["title"], "status": "skipped", "detail": "UI disabled"})
                    continue
                first = _execute(scenario, base_url, api, browser)
                attempts = [first["status"]]
                final = first
                for _ in range(retries):
                    if final["status"] != "failed":
                        break
                    retry = _execute(scenario, base_url, api, browser)
                    attempts.append(retry["status"])
                    if retry["status"] == "passed":
                        final = dict(first, status="flaky")
                    else:
                        final = retry
                final["attempts"] = attempts
                results.append(final)
        finally:
            if browser:
                browser.close()
            api.dispose()
    return results
