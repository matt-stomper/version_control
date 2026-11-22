import pytest

from version_control import project_version as version_control


def mock_git(monkeypatch, responses):
    def fake_git(*args):
        return responses[args]

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


def test_commits_since_uses_full_log_when_no_tag(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("log", "--format=%B"): "feat: initial release\nfix: first bug",
        },
    )

    assert version_control.commits_since(None) == [
        "feat: initial release",
        "fix: first bug",
    ]


def test_commits_since_uses_tag_range_when_tag_exists(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("log", "v1.0.0..HEAD", "--format=%B"): "fix: bug fix",
        },
    )

    assert version_control.commits_since("v1.0.0") == ["fix: bug fix"]


@pytest.mark.parametrize(
    ("message", "expected_bump"),
    [
        ("feat!: change public API", version_control.Bump.MAJOR),
        ("fix!: change public API", version_control.Bump.MAJOR),
        ("feat(api)!: change public API", version_control.Bump.MAJOR),
        ("fix: bug\n\nBREAKING CHANGE: incompatible change", version_control.Bump.MAJOR),
        ("fix: bug\n\nBREAKING-CHANGE: incompatible change", version_control.Bump.MAJOR),
        ("feat: add feature", version_control.Bump.MINOR),
        ("feat(api): add feature", version_control.Bump.MINOR),
        ("fix: fix bug", version_control.Bump.PATCH),
        ("fix(api): fix bug", version_control.Bump.PATCH),
        ("perf: improve speed", version_control.Bump.PATCH),
        ("perf(api): improve speed", version_control.Bump.PATCH),
        ("docs: update README", version_control.Bump.NONE),
        ("chore: update tooling", version_control.Bump.NONE),
        ("", version_control.Bump.NONE),
    ],
)
def test_bump_from_commit_message(message, expected_bump):
    assert version_control.bump_from_commit_message(message) == expected_bump


def test_bump_from_commits_returns_highest_required_bump():
    messages = [
        "docs: update README",
        "fix: fix bug",
        "feat: add feature",
        "chore: update tooling",
    ]

    assert version_control.bump_from_commits(messages) == version_control.Bump.MINOR


def test_next_version_on_main_with_patch_bump(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.2.3",
            ("log", "v1.2.3..HEAD", "--format=%B"): "fix: fix production bug",
        },
    )

    assert version_control.next_version(branch="main") == "1.2.4"


def test_next_version_on_main_with_minor_bump(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.2.3",
            ("log", "v1.2.3..HEAD", "--format=%B"): "feat: add reports",
        },
    )

    assert version_control.next_version(branch="main") == "1.3.0"


def test_next_version_on_main_with_major_bump(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.2.3",
            ("log", "v1.2.3..HEAD", "--format=%B"): "feat!: replace API",
        },
    )

    assert version_control.next_version(branch="main") == "2.0.0"


def test_next_version_on_main_with_no_bump(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.2.3",
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
            ("log", "v1.2.3..HEAD", "--format=%B"): "feat: add reports",
        },
    )

    assert version_control.next_version(branch="develop") == "1.3.0.dev0"


def test_next_version_on_release_branch_adds_rc_suffix(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.2.3",
            ("log", "v1.2.3..HEAD", "--format=%B"): "feat: add reports",
        },
    )

    assert version_control.next_version(branch="release/1.3.0") == "1.3.0-rc.0"


def test_next_version_on_feature_branch_adds_short_sha_build_suffix(monkeypatch):
    mock_git(
        monkeypatch,
        {
            ("tag", "--list"): "v1.2.3",
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
            ("log", "v1.2.3..HEAD", "--format=%B"): "feat: add reports",
            ("rev-parse", "--abbrev-ref", "HEAD"): "develop",
        },
    )

    assert version_control.next_version() == "1.3.0.dev0"


def test_release_branch_with_invalid_name_raises_value_error():
    version = version_control.Version(1, 2, 3)

    with pytest.raises(ValueError, match="Invalid release branch name"):
        version_control.validate_release_branch(version, "release/1.2")


def test_release_branch_with_mismatched_version_raises_value_error():
    version = version_control.Version(1, 2, 3)

    with pytest.raises(ValueError, match="Release branch version mismatch"):
        version_control.validate_release_branch(version, "release/1.2.4")


def test_version_parse_accepts_v_prefixed_tags():
    assert version_control.Version.parse("v1.2.3") == version_control.Version(1, 2, 3)


def test_version_parse_ignores_prerelease_dev_and_build_suffixes():
    assert version_control.Version.parse("1.2.3-rc.0") == version_control.Version(1, 2, 3)
    assert version_control.Version.parse("1.2.3.dev0") == version_control.Version(1, 2, 3)
    assert version_control.Version.parse("1.2.3+abc1234") == version_control.Version(1, 2, 3)


def test_version_parse_rejects_invalid_versions():
    with pytest.raises(ValueError, match="Invalid version tag"):
        version_control.Version.parse("not-a-version")