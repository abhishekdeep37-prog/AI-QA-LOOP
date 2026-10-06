"""Safe handling of LLM-proposed patches.

The model proposes a search/replace edit {file, old, new}. We never trust it:
the edit must match the source exactly once, must compile, and is verified by
running the whole suite against a patched COPY of the app before anyone sees it.
"""
import ast
import difflib
import shutil
import tempfile
from pathlib import Path

from qa.runner import run_scenarios
from qa.server_ctl import running_server


class PatchError(ValueError):
    pass


def apply_edit(source: str, old: str, new: str) -> str:
    if not isinstance(old, str) or not isinstance(new, str) or not old.strip():
        raise PatchError("edit needs non-empty 'old' and 'new' strings")
    count = source.count(old)
    if count == 0:
        raise PatchError("'old' text was not found in the file (it must be copied exactly)")
    if count > 1:
        raise PatchError(f"'old' text matches {count} places; it must match exactly once")
    patched = source.replace(old, new, 1)
    try:
        compile(patched, "<patched>", "exec")
    except SyntaxError as e:
        raise PatchError(f"patched file does not compile: {e.msg} (line {e.lineno})") from e
    return patched


def make_diff(path: str, before: str, after: str) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}"))


def changed_line_range(source: str, old: str) -> tuple:
    """1-based inclusive line range of `old` inside `source`."""
    idx = source.index(old)
    start = source.count("\n", 0, idx) + 1
    return start, start + old.count("\n")


def enclosing_functions(source: str, start: int, end: int) -> set:
    """Names of functions whose body overlaps the line range [start, end]."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= end and (node.end_lineno or node.lineno) >= start:
                names.add(node.name)
    return names


def changed_line_count(before: str, after: str) -> int:
    sm = difflib.SequenceMatcher(None, before.splitlines(), after.splitlines())
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")


def verify_patch(app_dir, rel_file: str, old: str, new: str, scenarios, baseline, ui=True) -> dict:
    """Apply the edit to a temporary copy of the app and rerun every scenario.

    `baseline` maps scenario id -> status from the unpatched run. The patch is
    "verified" only if the previously failing scenarios it targets now pass and
    nothing that passed before fails now. Returns evidence for the policy check.
    """
    app_dir = Path(app_dir)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / app_dir.name
        shutil.copytree(app_dir, copy, ignore=shutil.ignore_patterns("__pycache__"))
        target = copy / Path(rel_file).name
        target.write_text(apply_edit(target.read_text(), old, new))
        with running_server(copy) as url:
            results = run_scenarios(scenarios, url, ui=ui)
    after = {r["id"]: r["status"] for r in results}
    fixed = sorted(i for i, s in baseline.items() if s == "failed" and after.get(i) == "passed")
    regressions = sorted(i for i, s in baseline.items() if s in {"passed", "flaky"} and after.get(i) == "failed")
    still_failing = sorted(i for i, s in after.items() if s == "failed")
    return {"fixed": fixed, "regressions": regressions, "still_failing": still_failing}
