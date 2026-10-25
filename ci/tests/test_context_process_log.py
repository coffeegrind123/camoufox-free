"""The cross-process font guard must read Firefox 158's ProcessIsolation log."""

import importlib.util
from pathlib import Path

from ci._util import REPO_ROOT

SCRIPT = REPO_ROOT / "browser" / "tests" / "playwright" / "patches" / "context-lists-across-processes.py"
spec = importlib.util.spec_from_file_location("context_lists", SCRIPT)
context_lists = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context_lists)


def test_firefox_process_isolation_lines_name_the_origins(tmp_path):
    port = 43210
    (tmp_path / "cfx-main.log").write_text(
        "\n".join(
            [
                f"Using IsolationBehavior WebContent for http://eTLD+1: http://127.0.0.{i}:{port} "
                f"(original uri http://127.0.0.{i}:{port}/font-fallback.html?context=1)"
                for i in (1, 2)
            ]
            + [
                "Using IsolationBehavior WebContent for http://eTLD+1: http://127.0.0.3:1 "
                "(original uri http://127.0.0.3:1/font-fallback.html?context=1)",
                f"Using IsolationBehavior WebContent for http://eTLD+1: http://127.0.0.4:{port} "
                f"(original uri http://127.0.0.4:{port}/other.html)",
            ]
        ),
        encoding="utf-8",
    )
    assert context_lists.context_origins(tmp_path, port) == {
        "127.0.0.1": {"WebContent"},
        "127.0.0.2": {"WebContent"},
    }
