"""Generate a protocol-format release body from axon-dev cli/ commits.

Used by .github/workflows/auto-release.yml when a tag is pushed: pulls
the conventional-commit subjects from axon-dev's cli/ subtree in the
window since the previous tag, applies CLI-only filtering and emoji
mapping, and prints the body to stdout for `gh release create --notes`.

Logic mirrors axon-marketing's generate_release_tweet.py so the marketing
pipeline can consume the result without further translation.
"""

import argparse
import re
import subprocess

CLI_SCOPES = {"cli", "mining"}
EXCLUDED_SCOPES = {"webapp", "webapp2", "server"}

EMOJI_MAP = {
    "feat": "✨",
    "fix": "🔧",
    "docs": "📝",
    "ci": "🚀",
    "security": "🔒",
    "refactor": "♻️",
    "perf": "🏎️",
    "test": "🧪",
}

USER_FACING_TYPES = {"feat", "fix", "perf", "security"}


def parse_log_lines(stdout: str) -> list[str]:
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def clean_commit(msg: str) -> str:
    cleaned = re.sub(r"^[a-z]+(\([^)]*\))?:\s*", "", msg)
    cleaned = re.sub(r"\s*\(#\d+\)\s*$", "", cleaned)
    return cleaned[:1].upper() + cleaned[1:] if cleaned else cleaned


def get_commit_emoji(msg: str) -> str:
    match = re.match(r"^([a-z]+)", msg)
    if match:
        return EMOJI_MAP.get(match.group(1), "⚡")
    return "⚡"


def filter_cli_commits(commits: list[str]) -> list[str]:
    filtered = []
    for msg in commits:
        match = re.match(r"^[a-z]+\(([^)]*)\):", msg)
        if match:
            scope = match.group(1).lower()
            if scope in EXCLUDED_SCOPES:
                continue
        filtered.append(msg)
    return filtered


def is_chore_bump(msg: str) -> bool:
    """chore(cli): bump version ... — noise in every release."""
    return bool(re.match(r"^chore(\([^)]*\))?:\s*bump version", msg, re.IGNORECASE))


def format_body(commits: list[str]) -> str:
    cli_commits = filter_cli_commits(commits)
    lines = []
    for msg in cli_commits:
        if is_chore_bump(msg):
            continue
        match = re.match(r"^([a-z]+)", msg)
        commit_type = match.group(1) if match else ""
        if commit_type not in USER_FACING_TYPES:
            continue
        desc = clean_commit(msg)
        if not desc:
            continue
        lines.append(f"{get_commit_emoji(msg)} {desc}")
    return "\n".join(lines)


def get_commits(
    axon_dev_path: str, since: str, until: str | None = None, path: str = "cli"
) -> list[str]:
    cmd = [
        "git",
        "-C",
        axon_dev_path,
        "log",
        f"--since={since}",
        "--pretty=format:%s",
        "--no-merges",
    ]
    if until:
        cmd.append(f"--until={until}")
    cmd += ["--", path]
    output = subprocess.check_output(cmd).decode()
    return parse_log_lines(output)


def main():
    parser = argparse.ArgumentParser(description="Generate release body from axon-dev cli/ log")
    parser.add_argument("--tag", required=True, help="Current tag (e.g. v0.3.2)")
    parser.add_argument("--axon-dev-path", required=True, help="Path to axon-dev clone")
    parser.add_argument(
        "--prev-tag-time",
        required=True,
        help="ISO 8601 timestamp of the previous tag's release publish time",
    )
    parser.add_argument(
        "--current-tag-time",
        default=None,
        help="ISO 8601 upper bound (default: now). Used for historical dry-runs.",
    )
    parser.add_argument("--path", default="cli", help="Subdirectory in axon-dev to filter (default: cli)")
    args = parser.parse_args()

    commits = get_commits(args.axon_dev_path, args.prev_tag_time, args.current_tag_time, args.path)
    print(format_body(commits))


if __name__ == "__main__":
    main()
