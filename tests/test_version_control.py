import subprocess

import pytest

from version_control import project_version as version_control


def mock_git(monkeypatch, responses):
    def fake_git(*args):
        response = responses[args]

        if isinstance(response, Exception):
            raise response

        return response

    monkeypatch.setattr(version_control, "git", fake_git)


def test_git_lines_returns_split_lines(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.0.0\nv1.1.0\nv2.0.0",
        },
    )

    assert version_control.git_lines("tag", "--list") == [
        "v1.0.0",
        "v1.1.0",
        "v2.0.0",
    ]


def test_git_lines_returns_empty_list_for_empty_output(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "",
        },
    )

    assert version_control.git_lines("tag", "--list") == []


def test_current_branch_uses_git_rev_parse(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("rev-parse", "--abbrev-ref", "HEAD"): "develop",
        },
    )

    assert version_control.current_branch() == "develop"


def test_short_sha_uses_git_rev_parse(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("rev-parse", "--short", "HEAD"): "abc1234",
        },
    )

    assert version_control.short_sha() == "abc1234"


def test_all_version_tags_returns_semver_like_tags(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "\n".join(
                [
                    "v1.0.0",
                    "1.1.0",
                    "v2.0.0-rc.0",
                    "v2.0.0.dev0",
                    "v2.0.0+abc1234",
                    "not-a-version",
                    "release-1.0.0",
                ],
            ),
        },
    )

    assert version_control.all_version_tags() == [
        "v1.0.0",
        "1.1.0",
        "v2.0.0-rc.0",
        "v2.0.0.dev0",
        "v2.0.0+abc1234",
    ]


def test_stable_version_tags_filters_prerelease_dev_and_build_tags(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "\n".join(
                [
                    "v1.0.0",
                    "1.1.0",
                    "v2.0.0-rc.0",
                    "v2.0.0.dev0",
                    "v2.0.0+abc1234",
                ],
            ),
        },
    )

    assert version_control.stable_version_tags() == [
        "v1.0.0",
        "1.1.0",
    ]


def test_latest_stable_tag_returns_highest_semver_tag(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "\n".join(
                [
                    "v1.10.0",
                    "v1.2.9",
                    "v2.0.0",
                    "v2.0.1-rc.0",
                    "not-a-version",
                ],
            ),
        },
    )

    assert version_control.latest_stable_tag() == "v2.0.0"


def test_latest_stable_tag_returns_none_when_no_stable_tags(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "\n".join(
                [
                    "v1.0.0-rc.0",
                    "v1.0.0.dev0",
                    "not-a-version",
                ],
            ),
        },
    )

    assert version_control.latest_stable_tag() is None


def test_latest_branch_version_tag_returns_nearest_reachable_non_v_tag(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "0.1.0.dev0\n0.1.0\n0.2.0-rc.0",
            (
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                "[0-9]*.[0-9]*.[0-9]*",
            ): "0.1.0.dev0",
        },
    )

    assert version_control.latest_branch_version_tag() == "0.1.0.dev0"


def test_latest_branch_version_tag_falls_back_to_v_prefixed_tag(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v0.1.0.dev0",
            (
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                "[0-9]*.[0-9]*.[0-9]*",
            ): subprocess.CalledProcessError(1, "git describe"),
            (
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                "v[0-9]*.[0-9]*.[0-9]*",
            ): "v0.1.0.dev0",
        },
    )

    assert version_control.latest_branch_version_tag() == "v0.1.0.dev0"


def test_next_version_on_main_with_patch_bump(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.2.3",
            (
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                "[0-9]*.[0-9]*.[0-9]*",
            ): "v1.2.3",
            ("log", "v1.2.3..HEAD", "--format=%B"): "fix: fix production bug",
        },
    )

    assert version_control.next_version(branch="main") == "1.2.4"


def test_next_version_on_main_with_minor_bump(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.2.3",
            (
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                "[0-9]*.[0-9]*.[0-9]*",
            ): "v1.2.3",
            ("log", "v1.2.3..HEAD", "--format=%B"): "feat: add reports",
        },
    )

    assert version_control.next_version(branch="main") == "1.3.0"


def test_next_version_on_main_with_major_bump(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.2.3",
            (
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                "[0-9]*.[0-9]*.[0-9]*",
            ): "v1.2.3",
            ("log", "v1.2.3..HEAD", "--format=%B"): "feat!: replace API",
        },
    )

    assert version_control.next_version(branch="main") == "2.0.0"


def test_next_version_on_main_with_no_bump(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.2.3",
            (
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                "[0-9]*.[0-9]*.[0-9]*",
            ): "v1.2.3",
            ("log", "v1.2.3..HEAD", "--format=%B"): "docs: update README",
        },
    )

    assert version_control.next_version(branch="main") == "1.2.3"


def test_next_version_starts_from_zero_when_no_tags_exist(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "",
            ("log", "--format=%B"): "feat: initial feature",
        },
    )

    assert version_control.next_version(branch="main") == "0.1.0"


def test_next_version_on_develop_adds_dev_suffix(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.2.3",
            (
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                "[0-9]*.[0-9]*.[0-9]*",
            ): "v1.2.3",
            ("log", "v1.2.3..HEAD", "--format=%B"): "feat: add reports",
        },
    )

    assert version_control.next_version(branch="develop") == "1.3.0.dev0"


def test_next_version_on_release_branch_adds_rc_suffix(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.2.3",
            (
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                "[0-9]*.[0-9]*.[0-9]*",
            ): "v1.2.3",
            ("log", "v1.2.3..HEAD", "--format=%B"): "feat: add reports",
        },
    )

    assert version_control.next_version(branch="release/1.3.0") == "1.3.0-rc.0"


def test_next_version_on_feature_branch_adds_short_sha_build_suffix(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.2.3",
            (
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                "[0-9]*.[0-9]*.[0-9]*",
            ): "v1.2.3",
            ("log", "v1.2.3..HEAD", "--format=%B"): "fix: fix bug",
            ("rev-parse", "--short", "HEAD"): "abc1234",
        },
    )

    assert version_control.next_version(branch="feature/my-branch") == "1.2.4+abc1234"


def test_next_version_uses_current_branch_when_branch_is_not_provided(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.2.3",
            (
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                "[0-9]*.[0-9]*.[0-9]*",
            ): "v1.2.3",
            ("log", "v1.2.3..HEAD", "--format=%B"): "feat: add reports",
            ("rev-parse", "--abbrev-ref", "HEAD"): "develop",
        },
    )

    assert version_control.next_version() == "1.3.0.dev0"


def test_changelog_version_returns_base_version_without_dev_suffix(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "0.1.0.dev0",
            (
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                "[0-9]*.[0-9]*.[0-9]*",
            ): "0.1.0.dev0",
            ("log", "0.1.0.dev0..HEAD", "--format=%B"): "fix: fix dev bug",
        },
    )

    assert version_control.changelog_version(branch="develop") == "0.1.1"


def test_changelog_version_returns_base_version_without_rc_suffix(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "0.1.0.dev0",
            (
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                "[0-9]*.[0-9]*.[0-9]*",
            ): "0.1.0.dev0",
            ("log", "0.1.0.dev0..HEAD", "--format=%B"): "feat: add feature",
        },
    )

    assert version_control.changelog_version(branch="release/0.2.0") == "0.2.0"


def test_branch_changelog_uses_base_version_heading(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "0.1.0.dev0",
            (
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                "[0-9]*.[0-9]*.[0-9]*",
            ): "0.1.0.dev0",
            ("log", "0.1.0.dev0..HEAD", "--format=%B"): "fix: correct exported dependency",
            (
                "log",
                "0.1.0.dev0..HEAD",
                "--format=%H%x1f%s%x1f%B%x1e",
            ): "abc123456789\x1ffix: correct exported dependency\x1ffix: correct exported dependency\x1e",
        },
    )

    changelog = version_control.branch_changelog(branch="develop")

    assert changelog.startswith("## 0.1.1")
    assert "### Bug Fixes" in changelog
    assert "- correct exported dependency (abc1234)" in changelog

# ... existing code ...

def test_write_changelog_creates_changelog_file(tmp_path):
    changelog_path = tmp_path / "CHANGELOG.md"
    content = "## 0.1.0\n\n### Features\n\n- initial feature (abc1234)"

    version_control.write_changelog(content, path=str(changelog_path))

    assert changelog_path.read_text(encoding="utf-8") == (
        "## 0.1.0\n"
        "\n"
        "### Features\n"
        "\n"
        "- initial feature (abc1234)\n"
    )


def test_write_changelog_prepends_to_existing_changelog_file(tmp_path):
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text(
        "## 0.1.0\n"
        "\n"
        "### Features\n"
        "\n"
        "- initial feature (abc1234)\n",
        encoding="utf-8",
    )

    content = "## 0.1.1\n\n### Bug Fixes\n\n- fix bug (def5678)"

    version_control.write_changelog(content, path=str(changelog_path))

    assert changelog_path.read_text(encoding="utf-8") == (
        "## 0.1.1\n"
        "\n"
        "### Bug Fixes\n"
        "\n"
        "- fix bug (def5678)\n"
        "\n"
        "## 0.1.0\n"
        "\n"
        "### Features\n"
        "\n"
        "- initial feature (abc1234)\n"
    )


def test_write_changelog_raises_when_version_heading_already_exists(tmp_path):
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text(
        "## 0.1.0\n"
        "\n"
        "### Features\n"
        "\n"
        "- initial feature (abc1234)\n",
        encoding="utf-8",
    )

    content = "## 0.1.0\n\n### Bug Fixes\n\n- fix bug (def5678)"

    with pytest.raises(ValueError, match="Changelog already contains an entry for ## 0.1.0"):
        version_control.write_changelog(content, path=str(changelog_path))


def test_write_changelog_allows_different_version_heading(tmp_path):
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text(
        "## 0.1.0\n"
        "\n"
        "### Features\n"
        "\n"
        "- initial feature (abc1234)\n",
        encoding="utf-8",
    )

    content = "## 0.2.0\n\n### Features\n\n- add feature (def5678)"

    version_control.write_changelog(content, path=str(changelog_path))

    updated_content = changelog_path.read_text(encoding="utf-8")

    assert updated_content.startswith("## 0.2.0")
    assert "## 0.1.0" in updated_content

# ... existing code ...