#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from dataclasses import dataclass
from enum import IntEnum


CHANGELOG_FILE = "CHANGELOG.md"


class Bump(IntEnum):
    NONE = 0
    PATCH = 1
    MINOR = 2
    MAJOR = 3


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "Version":
        value = value.strip()

        if value.startswith("v"):
            value = value[1:]

        # Strip prerelease/build/dev suffixes so they never influence bumping.
        #
        # Examples:
        # 1.2.3-rc.0    -> 1.2.3
        # 1.2.3.dev0    -> 1.2.3
        # 1.2.3+abc1234 -> 1.2.3
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value)
        if not match:
            raise ValueError(f"Invalid version tag: {value}")

        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
        )

    def bump(self, bump: Bump) -> "Version":
        if bump == Bump.MAJOR:
            return Version(self.major + 1, 0, 0)

        if bump == Bump.MINOR:
            return Version(self.major, self.minor + 1, 0)

        if bump == Bump.PATCH:
            return Version(self.major, self.minor, self.patch + 1)

        return self

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ChangelogEntry:
    commit_hash: str
    subject: str
    commit_type: str
    scope: str | None
    description: str
    breaking: bool


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def git_lines(*args: str) -> list[str]:
    output = git(*args)
    if not output:
        return []
    return output.splitlines()


def current_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD")


def short_sha() -> str:
    return git("rev-parse", "--short", "HEAD")


def all_version_tags() -> list[str]:
    tags = git_lines("tag", "--list")

    version_tags: list[str] = []

    for tag in tags:
        raw = tag[1:] if tag.startswith("v") else tag

        if re.match(r"^\d+\.\d+\.\d+", raw):
            version_tags.append(tag)

    return version_tags


def stable_version_tags() -> list[str]:
    stable_tags: list[str] = []

    for tag in all_version_tags():
        raw = tag[1:] if tag.startswith("v") else tag

        if re.fullmatch(r"\d+\.\d+\.\d+", raw):
            stable_tags.append(tag)

    return stable_tags


def latest_stable_tag() -> str | None:
    tags = stable_version_tags()

    if not tags:
        return None

    def sort_key(tag: str) -> tuple[int, int, int]:
        version = Version.parse(tag)
        return version.major, version.minor, version.patch

    return sorted(tags, key=sort_key)[-1]


def previous_stable_tag(current_tag: str) -> str | None:
    stable_tags = stable_version_tags()

    if current_tag not in stable_tags:
        return None

    def sort_key(tag: str) -> tuple[int, int, int]:
        version = Version.parse(tag)
        return version.major, version.minor, version.patch

    sorted_tags = sorted(stable_tags, key=sort_key)
    current_index = sorted_tags.index(current_tag)

    if current_index == 0:
        return None

    return sorted_tags[current_index - 1]


def git_log_entries(from_tag: str | None, to_ref: str) -> list[tuple[str, str, str]]:
    revision_range = to_ref if from_tag is None else f"{from_tag}..{to_ref}"

    output = git(
        "log",
        revision_range,
        "--format=%H%x1f%s%x1f%B%x1e",
    )

    entries: list[tuple[str, str, str]] = []

    for raw_entry in output.strip("\x1e").split("\x1e"):
        raw_entry = raw_entry.strip()

        if not raw_entry:
            continue

        parts = raw_entry.split("\x1f", 2)

        if len(parts) != 3:
            continue

        commit_hash, subject, body = parts
        entries.append((commit_hash, subject, body))

    return entries


def parse_changelog_entry(commit_hash: str, subject: str, body: str) -> ChangelogEntry | None:
    breaking = "BREAKING CHANGE:" in body or "BREAKING-CHANGE:" in body

    match = re.match(
        r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?: (?P<description>.+)$",
        subject,
    )

    if not match:
        return None

    commit_type = match.group("type")
    scope = match.group("scope")
    description = match.group("description")

    if match.group("breaking"):
        breaking = True

    if commit_type not in {"feat", "fix", "perf"} and not breaking:
        return None

    return ChangelogEntry(
        commit_hash=commit_hash,
        subject=subject,
        commit_type=commit_type,
        scope=scope,
        description=description,
        breaking=breaking,
    )


def changelog_entries(from_tag: str | None, to_ref: str) -> list[ChangelogEntry]:
    entries: list[ChangelogEntry] = []

    for commit_hash, subject, body in git_log_entries(from_tag, to_ref):
        entry = parse_changelog_entry(commit_hash, subject, body)

        if entry is not None:
            entries.append(entry)

    return entries


def format_changelog_section(version: str, entries: list[ChangelogEntry]) -> str:
    lines: list[str] = [f"## {version}", ""]

    breaking_changes = [entry for entry in entries if entry.breaking]
    features = [entry for entry in entries if entry.commit_type == "feat" and not entry.breaking]
    fixes = [entry for entry in entries if entry.commit_type == "fix" and not entry.breaking]
    performance = [entry for entry in entries if entry.commit_type == "perf" and not entry.breaking]

    def append_group(title: str, grouped_entries: list[ChangelogEntry]) -> None:
        if not grouped_entries:
            return

        lines.append(f"### {title}")
        lines.append("")

        for entry in grouped_entries:
            scope = f"**{entry.scope}:** " if entry.scope else ""
            short_hash = entry.commit_hash[:7]
            lines.append(f"- {scope}{entry.description} ({short_hash})")

        lines.append("")

    append_group("Breaking Changes", breaking_changes)
    append_group("Features", features)
    append_group("Bug Fixes", fixes)
    append_group("Performance", performance)

    if len(lines) == 2:
        lines.append("No user-facing changes.")
        lines.append("")

    return "\n".join(lines).rstrip()


def write_changelog(content: str, path: str = CHANGELOG_FILE) -> None:
    heading = content.splitlines()[0]

    try:
        with open(path, "r", encoding="utf-8") as changelog_file:
            existing_content = changelog_file.read()
    except FileNotFoundError:
        existing_content = ""

    if heading in existing_content:
        raise ValueError(f"Changelog already contains an entry for {heading}.")

    if existing_content.strip():
        updated_content = f"{content}\n\n{existing_content}"
    else:
        updated_content = f"{content}\n"

    with open(path, "w", encoding="utf-8") as changelog_file:
        changelog_file.write(updated_content)


def stable_changelog() -> str:
    current_tag = latest_stable_tag()

    if current_tag is None:
        raise ValueError("No stable release tag found.")

    previous_tag = previous_stable_tag(current_tag)
    entries = changelog_entries(previous_tag, current_tag)

    return format_changelog_section(current_tag, entries)


def changelog_version(branch: str | None = None) -> str:
    version = next_version(branch=branch)
    return str(Version.parse(version))


def branch_changelog(branch: str | None = None) -> str:
    tag = latest_branch_version_tag()
    entries = changelog_entries(tag, "HEAD")
    version = changelog_version(branch=branch)

    return format_changelog_section(version, entries)


def latest_branch_version_tag() -> str | None:
    """
    Return the nearest reachable version tag from the current branch history.

    This intentionally includes prerelease/dev/build tags because dependency
    development branches should continue from their own last tagged version.

    Examples:
      0.1.0.dev0  -> base version 0.1.0
      0.2.0-rc0   -> base version 0.2.0
      0.2.0       -> base version 0.2.0
    """
    tags = all_version_tags()

    if not tags:
        return None

    try:
        return git("describe", "--tags", "--abbrev=0", "--match", "[0-9]*.[0-9]*.[0-9]*")
    except subprocess.CalledProcessError:
        pass

    try:
        return git("describe", "--tags", "--abbrev=0", "--match", "v[0-9]*.[0-9]*.[0-9]*")
    except subprocess.CalledProcessError:
        return None


def commits_since(tag: str | None) -> list[str]:
    if tag is None:
        return git_lines("log", "--format=%B")

    return git_lines("log", f"{tag}..HEAD", "--format=%B")


def bump_from_commit_message(message: str) -> Bump:
    """
    Conventional Commits bump rules.

    Major:
      feat!: something
      fix!: something
      BREAKING CHANGE: something

    Minor:
      feat: something

    Patch:
      fix: something
      perf: something

    No bump:
      docs, chore, ci, test, style, build, etc.
    """
    if "BREAKING CHANGE:" in message or "BREAKING-CHANGE:" in message:
        return Bump.MAJOR

    first_line = message.splitlines()[0] if message.splitlines() else ""

    if re.match(r"^[a-zA-Z]+(?:\([^)]+\))?!:", first_line):
        return Bump.MAJOR

    if re.match(r"^feat(?:\([^)]+\))?:", first_line):
        return Bump.MINOR

    if re.match(r"^(fix|perf)(?:\([^)]+\))?:", first_line):
        return Bump.PATCH

    return Bump.NONE


def bump_from_commits(messages: list[str]) -> Bump:
    bump = Bump.NONE

    for message in messages:
        bump = max(bump, bump_from_commit_message(message))

    return bump


def validate_release_branch(version: Version, branch: str) -> None:
    if not branch.startswith("release/"):
        return

    release_version = branch.removeprefix("release/")

    if not re.fullmatch(r"\d+\.\d+\.\d+", release_version):
        raise ValueError(
            f"Invalid release branch name '{branch}'. "
            "Release branches must use the format 'release/<major>.<minor>.<patch>', "
            "for example 'release/0.1.0'."
        )

    calculated_version = str(version)

    if release_version != calculated_version:
        raise ValueError(
            f"Release branch version mismatch. "
            f"Branch '{branch}' expects version '{release_version}', "
            f"but calculated version is '{calculated_version}'."
        )


def append_branch_suffix(version: Version, branch: str) -> str:
    base = str(version)

    if branch == "main":
        return base

    if branch.startswith("release/"):
        validate_release_branch(version, branch)
        return f"{base}-rc.0"

    if branch == "develop":
        return f"{base}.dev0"

    # Branch build
    return f"{base}+{short_sha()}"


def next_version(branch: str | None = None) -> str:
    tag = latest_branch_version_tag()

    if tag is None:
        current = Version(0, 0, 0)
    else:
        current = Version.parse(tag)

    messages = commits_since(tag)
    bump = bump_from_commits(messages)

    next_base = current.bump(bump)

    effective_branch = branch or current_branch()

    return append_branch_suffix(next_base, effective_branch)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate project versions and stable release changelogs.",
    )

    subparsers = parser.add_subparsers(dest="command")

    version_parser = subparsers.add_parser(
        "version",
        help="Calculate the next project version.",
    )

    version_parser.add_argument(
        "--branch",
        default=None,
        help="Branch name to use for prerelease/build suffix selection. Defaults to the current Git branch.",
    )

    subparsers.add_parser(
        "changelog",
        help="Generate the changelog for the latest stable release.",
    )

    parser.set_defaults(command="version")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    branch = getattr(args, "branch", None)

    if args.command == "changelog":
        changelog = branch_changelog(branch=branch)
        write_changelog(changelog)
        print(f"Wrote changelog to {CHANGELOG_FILE}")
        return

    print(next_version(branch=branch))


if __name__ == "__main__":
    main()