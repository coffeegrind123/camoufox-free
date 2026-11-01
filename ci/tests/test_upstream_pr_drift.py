"""ci/upstream_pr_drift.py: which lines of a diff count as content."""

from ci.upstream_pr_drift import content_lines, share


def test_patch_lines_match_without_their_own_prefix():
    # A line added inside a .patch file arrives as "++" in the outer diff.
    diff = "+++ b/browser/patches/x.patch\n++  return stock + SpoofedScreenShift(this).x.value;\n"
    assert content_lines(diff) == ["return stock + SpoofedScreenShift(this).x.value;"]


def test_regenerated_patch_headers_are_not_content():
    diff = ("+index 9a81697c6f..94fe84682d 100644\n"
            "+@@ -3788,12 +3788,54 @@ int32_t nsGlobalWindowInner::GetScreenY(CallerType aCallerType,\n"
            "+diff --git a/dom/events/Touch.cpp b/dom/events/Touch.cpp\n"
            "+// a comment that is long enough to count otherwise\n"
            "+short line\n")
    assert content_lines(diff) == []


def test_share_of_an_empty_diff_is_complete():
    assert share([], set()) == 100
    assert share(["a line long enough to count", "another line long enough"], {"a line long enough to count"}) == 50
