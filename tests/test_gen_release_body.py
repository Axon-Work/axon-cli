import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_parse_log_lines_strips_blanks():
    from gen_release_body import parse_log_lines

    stdout = "feat(cli): foo\n\nchore(cli): bar\n  \n"
    assert parse_log_lines(stdout) == ["feat(cli): foo", "chore(cli): bar"]


def test_format_body_v031_window():
    """Real v0.3.0..v0.3.1 axon-dev cli commits → expected body."""
    from gen_release_body import format_body

    commits = [
        "chore(cli): bump version to 0.3.1",
        "feat(cli): axon network → Network Pulse dashboard, parity with webapp",
    ]
    body = format_body(commits)

    # chore bump excluded
    assert "Bump version" not in body
    assert "0.3.1" not in body
    # feat present with emoji
    assert "✨" in body
    # description starts capitalized, no conventional prefix
    assert "feat(cli):" not in body
    assert "Axon network" in body or "axon network" in body.lower()


def test_format_body_filters_non_cli_scopes():
    from gen_release_body import format_body

    commits = [
        "feat(cli): keep cli scope",
        "feat(mining): keep mining scope",
        "feat: keep no scope",
        "feat(server): drop server scope",
        "feat(webapp): drop webapp scope",
        "feat(webapp2): drop webapp2 scope",
        "fix(server): drop server fix",
    ]
    body = format_body(commits).lower()

    assert "keep cli scope" in body
    assert "keep mining scope" in body
    assert "keep no scope" in body
    assert "drop server scope" not in body
    assert "drop webapp scope" not in body
    assert "drop webapp2 scope" not in body
    assert "drop server fix" not in body


def test_format_body_excludes_chore_bump_version():
    """chore(cli): bump version ... must be filtered, since it's noise in
    every release."""
    from gen_release_body import format_body

    commits = [
        "chore(cli): bump version to 0.3.1",
        "chore(cli): bump version to 1.0.0",
        "chore: bump version (#21)",
        "feat(cli): real feature",
    ]
    body = format_body(commits)

    assert "Bump version" not in body
    assert "real feature" in body.lower()


def test_format_body_emoji_mapping_for_user_facing_types():
    from gen_release_body import format_body

    commits = [
        "feat(cli): new thing",
        "fix(cli): broken thing",
        "perf(cli): faster thing",
        "security: harden it",
    ]
    body = format_body(commits)

    assert "✨" in body
    assert "🔧" in body
    assert "🏎️" in body
    assert "🔒" in body


def test_format_body_excludes_internal_types():
    """docs/test/refactor/chore (non-bump)/ci aren't user-facing — drop them
    so release body and tweet stay focused on what changed for users."""
    from gen_release_body import format_body

    commits = [
        "feat(cli): user-facing thing",
        "docs(cli): claude.md sync",
        "test(cli): align tests",
        "refactor(cli): internal refactor",
        "chore(cli): add type annotations",
        "ci: bump action",
    ]
    body = format_body(commits).lower()

    assert "user-facing thing" in body
    assert "claude.md" not in body
    assert "align tests" not in body
    assert "internal refactor" not in body
    assert "type annotations" not in body
    assert "bump action" not in body


def test_format_body_strips_pr_suffix():
    """git log subjects often end with ' (#NN)' — strip it from the description."""
    from gen_release_body import format_body

    commits = ["feat(cli): cool thing (#42)"]
    body = format_body(commits)

    assert "(#42)" not in body
    assert "Cool thing" in body


def test_format_body_empty_returns_empty_string():
    from gen_release_body import format_body

    assert format_body([]) == ""
    # only chore bump → after filtering, empty
    assert format_body(["chore(cli): bump version to 1.0.0"]) == ""
