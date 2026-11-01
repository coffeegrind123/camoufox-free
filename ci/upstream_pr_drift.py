"""How far each pull request this fork got merged upstream has drifted.

Upstream often merges a pull request in its own form: it squashes, renames,
rewrites and follows up, while this fork keeps the version it wrote. Both trees
then ship the change, quietly differently. For every merged pull request by
--author, this reports two shares of the lines the merge added (at least 20
characters, not comments; .patch files compared without their own +/- prefix
and hunk headers, so a patch regenerated on a newer Firefox still matches):

  upstream->fork  how much of what upstream merged is in this fork's tree
  fork->upstream  how much of the pull request's own head is in upstream's tree

A share below 100% names a difference to resolve: take upstream's form at the
next sync, or keep ours and record it in README.md ("What this fork adds").

    python3 -m ci.upstream_pr_drift --author <login> [--since YYYY-MM-DD]

Needs remotes `up` (daijro/camoufox) and `origin` (this fork), and `gh`.
"""

import argparse
import json
import re
import subprocess
from typing import Iterable, List, Set

from ci._util import REPO_ROOT
UPSTREAM = "daijro/camoufox"
BINARY = re.compile(r"\.(db|png|jpg|onnx|bin|zip|woff2?|ttf|otf|ttc)$")
# Lines that are not content: comments, docstring fences, and the headers a
# regenerated .patch carries.
NOT_CONTENT = ("#", "//", "*", '"""', "index ", "@@ ", "diff --git")
MIN_LEN = 20


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True,
                          text=True, errors="replace", check=False).stdout


def normalize(line: str) -> str:
    """A line as content: stripped, and without a .patch file's own +/- prefix."""
    line = line.strip()
    if line[:1] in "+- " and len(line) > 1:
        line = line[1:].strip()
    return line


def content_lines(diff: str) -> List[str]:
    """The added lines of a diff that count as content."""
    added = (normalize(l[1:]) for l in diff.split("\n") if l.startswith("+") and not l.startswith("+++"))
    return [l for l in added if len(l) >= MIN_LEN and not l.startswith(NOT_CONTENT)]


def tree_lines(ref: str) -> Set[str]:
    lines: Set[str] = set()
    for path in git("ls-tree", "-r", "--name-only", ref).split("\n"):
        if path and not BINARY.search(path):
            lines.update(normalize(l) for l in git("show", f"{ref}:{path}").split("\n"))
    return lines


def share(lines: List[str], tree: Set[str]) -> int:
    return 100 * sum(l in tree for l in lines) // len(lines) if lines else 100


def merged_prs(author: str, since: str) -> Iterable[dict]:
    query = f"author:{author} is:merged" + (f" merged:>={since}" if since else "")
    out = subprocess.run(["gh", "pr", "list", "-R", UPSTREAM, "--state", "merged", "--search", query,
                          "--limit", "1000", "--json", "number,title,mergeCommit"],
                         capture_output=True, text=True, check=True).stdout
    return sorted(json.loads(out), key=lambda pr: pr["number"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--author", required=True, help="GitHub login whose merged pull requests to check")
    parser.add_argument("--since", default="", help="only pull requests merged on or after this date")
    parser.add_argument("--show", type=int, default=8, help="missing lines to print per direction")
    args = parser.parse_args(argv)

    ours, theirs = tree_lines("origin/main"), tree_lines("up/main")
    for pr in merged_prs(args.author, args.since):
        number, merge = pr["number"], pr["mergeCommit"]["oid"]
        upstream_form = content_lines(git("diff", f"{merge}^1", merge))
        git("fetch", "-q", "up", f"pull/{number}/head:refs/remotes/up/pr/{number}")
        base = git("merge-base", f"up/pr/{number}", f"{merge}^1").strip()
        our_form = content_lines(git("diff", base, f"up/pr/{number}"))
        to_fork, to_upstream = share(upstream_form, ours), share(our_form, theirs)
        print(f"#{number}  upstream->fork {to_fork:3d}%  fork->upstream {to_upstream:3d}%  {pr['title']}")
        for label, lines, tree in (("not in fork", upstream_form, ours), ("not upstream", our_form, theirs)):
            for line in [l for l in lines if l not in tree][:args.show]:
                print(f"    {label}: {line[:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
