#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from enum import IntEnum


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
    """
    Return only stable SemVer tags.

    These are allowed:
      v1.2.3
      1.2.3

    These are ignored:
      v1.2.3-rc.0
      v1.2.3.dev0
      v1.2.3+abc1234
    """
    stable_tags: list[str] = []

    for tag in all_version_tags():
        raw = tag[1:] if tag.startswith("v") else tag

        if re.match(r"^\d+\.\d+\.\d+$", raw):
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
    tag = latest_stable_tag()

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
        description="Calculate the next project version from Git tags and commits.",
    )

    parser.add_argument(
        "--branch",
        default=None,
        help="Branch name to use for prerelease/build suffix selection. Defaults to the current Git branch.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(next_version(branch=args.branch))


if __name__ == "__main__":
    main()