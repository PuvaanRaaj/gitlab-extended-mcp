"""Unit tests for server.py's pure slimming/compaction helper functions."""

import os

os.environ.setdefault("GITLAB_TOKEN", "dummy")

from server import (
    _compact,
    _priority_from_labels,
    _slim_commit,
    _slim_diff,
    _slim_discussion,
    _slim_issue,
    _slim_job,
    _slim_label,
    _slim_member,
    _slim_mr,
    _slim_note,
    _slim_pipeline,
    _slim_project,
)


# ── _compact ────────────────────────────────────────────────────────────────

def test_compact_strips_none_empty_list_empty_dict():
    assert _compact({"a": None, "b": [], "c": {}, "d": "keep"}) == {"d": "keep"}


def test_compact_keeps_falsy_but_meaningful_values():
    assert _compact({"a": 0, "b": False, "c": ""}) == {"a": 0, "b": False, "c": ""}


def test_compact_recurses_into_nested_dicts_and_lists():
    nested = {"a": {"b": None, "c": "keep"}, "d": [{"e": None, "f": 1}]}
    assert _compact(nested) == {"a": {"c": "keep"}, "d": [{"f": 1}]}


def test_compact_passthrough_scalar():
    assert _compact("just a string") == "just a string"
    assert _compact(42) == 42


# ── _slim_mr ────────────────────────────────────────────────────────────────

def test_slim_mr_full_fields():
    mr = {
        "iid": 5,
        "title": "Fix bug",
        "state": "opened",
        "draft": True,
        "author": {"username": "puvaan"},
        "assignees": [{"username": "alice"}],
        "reviewers": [{"username": "bob"}],
        "labels": ["bug"],
        "source_branch": "fix/bug",
        "target_branch": "main",
        "detailed_merge_status": "mergeable",
        "sha": "abc123",
        "diff_refs": {"base_sha": "x"},
        "web_url": "https://gitlab.example.com/mr/5",
        "created_at": "2026-01-01T00:00:00Z",
        "merged_at": None,
    }
    slim = _slim_mr(mr)
    assert slim["iid"] == 5
    assert slim["author"] == "puvaan"
    assert slim["assignees"] == ["alice"]
    assert slim["reviewers"] == ["bob"]
    assert slim["merge_status"] == "mergeable"
    assert "merged_at" not in slim  # None stripped


def test_slim_mr_empty_assignees_and_reviewers_omitted():
    mr = {"iid": 1, "author": {}, "assignees": [], "reviewers": []}
    slim = _slim_mr(mr)
    assert "assignees" not in slim
    assert "reviewers" not in slim
    assert "author" not in slim  # missing username -> None -> stripped


def test_slim_mr_draft_false_is_stripped():
    mr = {"iid": 1, "draft": False}
    assert "draft" not in _slim_mr(mr)


# ── _slim_issue ─────────────────────────────────────────────────────────────

def test_slim_issue_basic():
    issue = {
        "iid": 10,
        "title": "Bug report",
        "description": "",
        "state": "opened",
        "author": {"username": "carol"},
        "assignees": [{"username": "dave"}],
        "labels": ["P1"],
        "milestone": {"title": "v1.0"},
        "web_url": "https://gitlab.example.com/issues/10",
        "created_at": "2026-01-01T00:00:00Z",
        "closed_at": None,
    }
    slim = _slim_issue(issue)
    assert slim["milestone"] == "v1.0"
    assert slim["assignees"] == ["dave"]
    assert "description" not in slim  # empty string -> None -> stripped
    assert "closed_at" not in slim


# ── _slim_pipeline ──────────────────────────────────────────────────────────

def test_slim_pipeline_truncates_sha():
    p = {"id": 1, "iid": 2, "status": "success", "ref": "main",
         "sha": "0123456789abcdef", "source": "push", "web_url": "u",
         "created_at": "t"}
    assert _slim_pipeline(p)["sha"] == "01234567"


def test_slim_pipeline_no_sha():
    p = {"id": 1, "status": "success"}
    assert "sha" not in _slim_pipeline(p)


# ── _slim_job ───────────────────────────────────────────────────────────────

def test_slim_job_rounds_duration():
    j = {"id": 1, "name": "build", "stage": "test", "status": "success",
         "duration": 12.3456}
    assert _slim_job(j)["duration_s"] == 12.3


def test_slim_job_no_duration_omitted():
    j = {"id": 1, "name": "build", "duration": None}
    assert "duration_s" not in _slim_job(j)


# ── _slim_commit ────────────────────────────────────────────────────────────

def test_slim_commit_prefers_short_id():
    c = {"short_id": "abc1234", "id": "abc1234567890", "title": "msg",
         "author_name": "eve", "committed_date": "t"}
    assert _slim_commit(c)["sha"] == "abc1234"


def test_slim_commit_falls_back_to_truncated_id():
    c = {"id": "abcdef0123456789", "title": "msg", "author_name": "eve",
         "created_at": "t"}
    assert _slim_commit(c)["sha"] == "abcdef01"


# ── _slim_note / _slim_discussion ────────────────────────────────────────────

def test_slim_note_extracts_position():
    n = {"id": 1, "author": {"username": "frank"}, "body": "lgtm",
         "created_at": "t", "resolved": True,
         "position": {"new_path": "a.py", "new_line": 42}}
    slim = _slim_note(n)
    assert slim["file"] == "a.py"
    assert slim["line"] == 42
    assert slim["resolved"] is True


def test_slim_note_resolved_false_stripped():
    n = {"id": 1, "resolved": False}
    assert "resolved" not in _slim_note(n)


def test_slim_discussion_filters_system_notes():
    d = {"id": "disc1", "notes": [
        {"id": 1, "body": "hello", "system": False},
        {"id": 2, "body": "changed status", "system": True},
    ]}
    slim = _slim_discussion(d)
    assert slim["id"] == "disc1"
    assert len(slim["notes"]) == 1
    assert slim["notes"][0]["body"] == "hello"


def test_slim_discussion_all_system_returns_none():
    d = {"id": "disc1", "notes": [{"id": 1, "system": True}]}
    assert _slim_discussion(d) is None


# ── _slim_label / _slim_member / _slim_project ──────────────────────────────

def test_slim_label():
    lb = {"id": 1, "name": "bug", "color": "#ff0000", "description": None}
    slim = _slim_label(lb)
    assert slim == {"id": 1, "name": "bug", "color": "#ff0000"}


def test_slim_member_maps_access_level():
    m = {"id": 1, "username": "gina", "name": "Gina", "access_level": 40}
    assert _slim_member(m)["access"] == "Maintainer"


def test_slim_member_unknown_access_level_falls_back_to_str():
    m = {"id": 1, "username": "gina", "access_level": 99}
    assert _slim_member(m)["access"] == "99"


def test_slim_project():
    p = {"id": 1, "path_with_namespace": "group/proj", "description": None,
         "default_branch": "main", "visibility": "private",
         "web_url": "u", "star_count": 0, "open_issues_count": 5,
         "last_activity_at": "t"}
    slim = _slim_project(p)
    assert slim["path"] == "group/proj"
    assert slim["star_count"] == 0  # falsy-but-meaningful, kept
    assert "description" not in slim


# ── _slim_diff ──────────────────────────────────────────────────────────────

def test_slim_diff_no_truncation_under_limit():
    d = {"new_path": "a.py", "old_path": "a.py", "diff": "line1\nline2"}
    slim = _slim_diff(d)
    assert slim["diff"] == "line1\nline2"
    assert "old_path" not in slim  # same as new_path -> stripped


def test_slim_diff_truncates_over_max_lines():
    d = {"new_path": "a.py", "diff": "\n".join(f"line{i}" for i in range(200))}
    slim = _slim_diff(d, max_lines=150)
    lines = slim["diff"].splitlines()
    assert len(lines) == 151  # 150 kept + truncation marker
    assert lines[-1] == "[...truncated]"


def test_slim_diff_renamed_file_path_kept_when_different():
    d = {"new_path": "b.py", "old_path": "a.py", "diff": "x"}
    slim = _slim_diff(d)
    assert slim["old_path"] == "a.py"
    assert slim["new_path"] == "b.py"


# ── _priority_from_labels ────────────────────────────────────────────────────

def test_priority_from_labels_case_insensitive_match():
    assert _priority_from_labels(["bug", "p1"], ["P1", "P2"]) == "P1"


def test_priority_from_labels_no_match_returns_none():
    assert _priority_from_labels(["bug"], ["P1", "P2"]) is None


def test_priority_from_labels_returns_first_matching_priority_in_order():
    assert _priority_from_labels(["P2", "P1"], ["P1", "P2"]) == "P1"
