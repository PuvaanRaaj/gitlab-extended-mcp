#!/usr/bin/env python3
"""
GitLab Extended MCP Server

Drop-in replacement for the official Claude GitLab plugin with:
  - All official plugin tools replicated
  - Additional tools not in the official plugin
  - Token-efficient responses (slimmed objects, nulls stripped, diffs truncated)

Auth: GITLAB_URL + GITLAB_TOKEN env vars (same as the official plugin).
"""

from __future__ import annotations

import os
import sys
from typing import Optional
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP

GITLAB_URL: str = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
GITLAB_TOKEN: str = os.environ.get("GITLAB_TOKEN", "")

mcp = FastMCP(
    "gitlab-extended",
    instructions="GitLab tools with token-efficient responses. Covers all official plugin tools plus MR discussions, approvals, job logs, file browsing, and more.",
)


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _api(path: str) -> str:
    return f"{GITLAB_URL}/api/v4/{path.lstrip('/')}"

def _gql() -> str:
    return f"{GITLAB_URL}/api/graphql"

def _h() -> dict[str, str]:
    return {"PRIVATE-TOKEN": GITLAB_TOKEN}

def _pid(project_id: str) -> str:
    return quote(str(project_id), safe="")

def _gid(group_id: str) -> str:
    return quote(str(group_id), safe="")

def _get(path: str, **params) -> object:
    with httpx.Client(timeout=30) as c:
        r = c.get(_api(path), headers=_h(), params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()

def _post(path: str, body: dict) -> object:
    with httpx.Client(timeout=30) as c:
        r = c.post(_api(path), headers=_h(), json=body)
        r.raise_for_status()
        return r.json()

def _put(path: str, body: dict) -> object:
    with httpx.Client(timeout=30) as c:
        r = c.put(_api(path), headers=_h(), json=body)
        r.raise_for_status()
        return r.json()

def _delete(path: str) -> object:
    with httpx.Client(timeout=30) as c:
        r = c.delete(_api(path), headers=_h())
        r.raise_for_status()
        return r.json() if r.content else {"status": "deleted"}

def _text(path: str) -> str:
    with httpx.Client(timeout=60) as c:
        r = c.get(_api(path), headers=_h())
        r.raise_for_status()
        return r.text

def _graphql(query: str, variables: dict) -> dict:
    with httpx.Client(timeout=30) as c:
        r = c.post(_gql(), headers=_h(), json={"query": query, "variables": variables})
        r.raise_for_status()
        return r.json()


# ── Token-efficiency helpers ──────────────────────────────────────────────────

def _compact(obj: object) -> object:
    """Recursively strip None, empty lists, and empty dicts."""
    if isinstance(obj, dict):
        return {k: _compact(v) for k, v in obj.items()
                if v is not None and v != [] and v != {}}
    if isinstance(obj, list):
        return [_compact(i) for i in obj]
    return obj

def _slim_mr(mr: dict) -> dict:
    return _compact({
        "iid": mr.get("iid"),
        "title": mr.get("title"),
        "state": mr.get("state"),
        "draft": mr.get("draft") or None,
        "author": mr.get("author", {}).get("username"),
        "assignees": [a["username"] for a in mr.get("assignees", [])] or None,
        "reviewers": [r["username"] for r in mr.get("reviewers", [])] or None,
        "labels": mr.get("labels") or None,
        "source_branch": mr.get("source_branch"),
        "target_branch": mr.get("target_branch"),
        "merge_status": mr.get("detailed_merge_status"),
        "sha": mr.get("sha"),
        "diff_refs": mr.get("diff_refs"),
        "web_url": mr.get("web_url"),
        "created_at": mr.get("created_at"),
        "merged_at": mr.get("merged_at"),
    })

def _slim_issue(issue: dict) -> dict:
    return _compact({
        "iid": issue.get("iid"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "author": issue.get("author", {}).get("username"),
        "assignees": [a["username"] for a in issue.get("assignees", [])] or None,
        "labels": issue.get("labels") or None,
        "milestone": (issue.get("milestone") or {}).get("title"),
        "web_url": issue.get("web_url"),
        "created_at": issue.get("created_at"),
        "closed_at": issue.get("closed_at"),
    })

def _slim_pipeline(p: dict) -> dict:
    return _compact({
        "id": p.get("id"),
        "iid": p.get("iid"),
        "status": p.get("status"),
        "ref": p.get("ref"),
        "sha": p.get("sha", "")[:8] if p.get("sha") else None,
        "source": p.get("source"),
        "web_url": p.get("web_url"),
        "created_at": p.get("created_at"),
    })

def _slim_job(j: dict) -> dict:
    dur = j.get("duration")
    return _compact({
        "id": j.get("id"),
        "name": j.get("name"),
        "stage": j.get("stage"),
        "status": j.get("status"),
        "duration_s": round(dur, 1) if dur else None,
        "web_url": j.get("web_url"),
        "started_at": j.get("started_at"),
        "finished_at": j.get("finished_at"),
    })

def _slim_commit(c: dict) -> dict:
    return _compact({
        "sha": c.get("short_id") or (c.get("id") or "")[:8],
        "title": c.get("title"),
        "author": c.get("author_name"),
        "date": c.get("committed_date") or c.get("created_at"),
        "web_url": c.get("web_url"),
    })

def _slim_note(n: dict) -> dict:
    pos = n.get("position") or {}
    return _compact({
        "id": n.get("id"),
        "author": (n.get("author") or {}).get("username"),
        "body": n.get("body"),
        "created_at": n.get("created_at"),
        "resolved": n.get("resolved") or None,
        "file": pos.get("new_path"),
        "line": pos.get("new_line"),
    })

def _slim_discussion(d: dict) -> dict | None:
    notes = [_slim_note(n) for n in d.get("notes", []) if not n.get("system")]
    if not notes:
        return None
    return _compact({"id": d["id"], "notes": notes})

def _slim_label(lb: dict) -> dict:
    return _compact({
        "id": lb.get("id"),
        "name": lb.get("name"),
        "color": lb.get("color"),
        "description": lb.get("description") or None,
    })

def _slim_diff(d: dict, max_lines: int = 150) -> dict:
    raw = d.get("diff", "")
    lines = raw.splitlines()
    truncated = len(lines) > max_lines
    return _compact({
        "new_path": d.get("new_path"),
        "old_path": d.get("old_path") if d.get("old_path") != d.get("new_path") else None,
        "new_file": d.get("new_file") or None,
        "deleted_file": d.get("deleted_file") or None,
        "renamed_file": d.get("renamed_file") or None,
        "diff": "\n".join(lines[:max_lines]) + ("\n[...truncated]" if truncated else ""),
    })

def _slim_member(m: dict) -> dict:
    levels = {10: "Guest", 20: "Reporter", 30: "Developer", 40: "Maintainer", 50: "Owner"}
    lvl = m.get("access_level", 0)
    return _compact({
        "id": m.get("id"),
        "username": m.get("username"),
        "name": m.get("name"),
        "access": levels.get(lvl, str(lvl)),
    })

def _slim_project(p: dict) -> dict:
    return _compact({
        "id": p.get("id"),
        "path": p.get("path_with_namespace"),
        "description": p.get("description") or None,
        "default_branch": p.get("default_branch"),
        "visibility": p.get("visibility"),
        "web_url": p.get("web_url"),
        "star_count": p.get("star_count"),
        "open_issues_count": p.get("open_issues_count"),
        "last_activity_at": p.get("last_activity_at"),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_project(id: str) -> dict:
    """Get project metadata (default branch, visibility, URL, open issue count)."""
    return _slim_project(_get(f"projects/{_pid(id)}"))


# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH  (official plugin parity)
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def search(
    scope: str,
    search: str,
    project_id: Optional[str] = None,
    group_id: Optional[str] = None,
    state: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> object:
    """
    Search across GitLab. scope: issues, merge_requests, blobs, commits, notes,
    projects, milestones, users, wiki_blobs, snippet_titles.
    Provide project_id or group_id to scope the search.
    """
    if project_id:
        path = f"projects/{_pid(project_id)}/search"
    elif group_id:
        path = f"groups/{_gid(group_id)}/search"
    else:
        path = "search"

    results = _get(path, scope=scope, search=search, state=state, page=page, per_page=per_page)
    if not isinstance(results, list):
        return results

    # slim based on scope
    if scope == "merge_requests":
        return [_slim_mr(r) for r in results]
    if scope == "issues":
        return [_slim_issue(r) for r in results]
    if scope == "commits":
        return [_slim_commit(r) for r in results]
    if scope == "blobs":
        return [_compact({
            "filename": r.get("filename"),
            "ref": r.get("ref"),
            "startline": r.get("startline"),
            "data": (r.get("data") or "")[:500],
            "project_id": r.get("project_id"),
        }) for r in results]
    # notes, projects, users — return as-is but compacted
    return [_compact(r) for r in results]


@mcp.tool()
def search_labels(
    full_path: str,
    is_project: bool,
    search: Optional[str] = None,
) -> object:
    """Search labels in a project or group by title."""
    if is_project:
        path = f"projects/{_pid(full_path)}/labels"
    else:
        path = f"groups/{_gid(full_path)}/labels"
    results = _get(path, search=search, per_page=100)
    return [_slim_label(lb) for lb in (results if isinstance(results, list) else [])]


@mcp.tool()
def list_project_labels(
    project_id: str,
    search: Optional[str] = None,
    with_counts: bool = False,
) -> object:
    """List all labels for a project, optionally filtered by name."""
    results = _get(f"projects/{_pid(project_id)}/labels", search=search,
                   with_counts=with_counts, per_page=100)
    return [_slim_label(lb) for lb in (results if isinstance(results, list) else [])]


# ═══════════════════════════════════════════════════════════════════════════════
# MERGE REQUESTS  (official plugin parity + extended)
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_merge_request(id: str, merge_request_iid: int) -> dict:
    """Get a single merge request. Returns slimmed object with diff_refs for inline comments."""
    return _slim_mr(_get(f"projects/{_pid(id)}/merge_requests/{merge_request_iid}"))


@mcp.tool()
def list_project_mrs(
    project_id: str,
    state: str = "opened",
    author_username: Optional[str] = None,
    labels: Optional[str] = None,
    target_branch: Optional[str] = None,
    source_branch: Optional[str] = None,
    search: Optional[str] = None,
    order_by: str = "updated_at",
    sort: str = "desc",
    page: int = 1,
    per_page: int = 20,
) -> object:
    """List MRs for a project. state: opened|closed|merged|all."""
    results = _get(
        f"projects/{_pid(project_id)}/merge_requests",
        state=state, author_username=author_username, labels=labels,
        target_branch=target_branch, source_branch=source_branch,
        search=search, order_by=order_by, sort=sort, page=page, per_page=per_page,
    )
    return [_slim_mr(mr) for mr in (results if isinstance(results, list) else [])]


@mcp.tool()
def create_merge_request(
    id: str,
    title: str,
    source_branch: str,
    target_branch: str,
    description: Optional[str] = None,
    labels: Optional[str] = None,
    assignee_ids: Optional[list[int]] = None,
    reviewer_ids: Optional[list[int]] = None,
    milestone_id: Optional[int] = None,
    target_project_id: Optional[int] = None,
) -> dict:
    """Create a new merge request."""
    body = _compact({
        "title": title,
        "source_branch": source_branch,
        "target_branch": target_branch,
        "description": description,
        "labels": labels,
        "assignee_ids": assignee_ids,
        "reviewer_ids": reviewer_ids,
        "milestone_id": milestone_id,
        "target_project_id": target_project_id,
    })
    return _slim_mr(_post(f"projects/{_pid(id)}/merge_requests", body))


@mcp.tool()
def update_mr(
    project_id: str,
    mr_iid: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    labels: Optional[str] = None,
    add_labels: Optional[str] = None,
    remove_labels: Optional[str] = None,
    assignee_ids: Optional[list[int]] = None,
    reviewer_ids: Optional[list[int]] = None,
    target_branch: Optional[str] = None,
    state_event: Optional[str] = None,
) -> dict:
    """Update MR fields. state_event: close|reopen."""
    body = _compact({
        "title": title, "description": description, "labels": labels,
        "add_labels": add_labels, "remove_labels": remove_labels,
        "assignee_ids": assignee_ids, "reviewer_ids": reviewer_ids,
        "target_branch": target_branch, "state_event": state_event,
    })
    return _slim_mr(_put(f"projects/{_pid(project_id)}/merge_requests/{mr_iid}", body))


@mcp.tool()
def get_merge_request_diffs(
    id: str,
    merge_request_iid: int,
    page: int = 1,
    per_page: int = 20,
) -> object:
    """
    Get file diffs for an MR. Each diff is truncated at 150 lines.
    Use get_file_at_ref to read full file content.
    """
    results = _get(
        f"projects/{_pid(id)}/merge_requests/{merge_request_iid}/diffs",
        page=page, per_page=per_page,
    )
    if isinstance(results, dict) and "diffs" in results:
        # Some GitLab versions return {diffs: [...], ...}
        return [_slim_diff(d) for d in results["diffs"]]
    return [_slim_diff(d) for d in (results if isinstance(results, list) else [])]


@mcp.tool()
def get_mr_diff_stats(project_id: str, mr_iid: int) -> object:
    """File-level stats (additions/deletions counts) without diff content. Cheaper than get_merge_request_diffs."""
    changes = _get(f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/changes")
    diffs = changes.get("changes", []) if isinstance(changes, dict) else []
    return [_compact({
        "path": d.get("new_path"),
        "old_path": d.get("old_path") if d.get("old_path") != d.get("new_path") else None,
        "new_file": d.get("new_file") or None,
        "deleted": d.get("deleted_file") or None,
        "renamed": d.get("renamed_file") or None,
        "added": (d.get("diff") or "").count("\n+"),
        "removed": (d.get("diff") or "").count("\n-"),
    }) for d in diffs]


@mcp.tool()
def get_merge_request_commits(
    id: str,
    merge_request_iid: int,
    page: int = 1,
    per_page: int = 20,
) -> object:
    """List commits in an MR (slimmed: sha, title, author, date)."""
    results = _get(
        f"projects/{_pid(id)}/merge_requests/{merge_request_iid}/commits",
        page=page, per_page=per_page,
    )
    return [_slim_commit(c) for c in (results if isinstance(results, list) else [])]


@mcp.tool()
def get_merge_request_conflicts(project_id: str, merge_request_iid: int) -> str:
    """Return raw git conflict markers for a conflicted MR."""
    try:
        data = _get(f"projects/{_pid(project_id)}/merge_requests/{merge_request_iid}/conflicts")
        if isinstance(data, dict) and "files" in data:
            out = []
            for f in data["files"]:
                out.append(f"=== {f.get('new_path', '')} ===")
                out.append(f.get("content_sections_as_text") or f.get("diff") or "")
            return "\n".join(out)
        return str(data)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return "MR has no conflicts or cannot be checked."
        raise


@mcp.tool()
def get_merge_request_pipelines(id: str, merge_request_iid: int) -> object:
    """List pipelines triggered for an MR."""
    results = _get(f"projects/{_pid(id)}/merge_requests/{merge_request_iid}/pipelines")
    return [_slim_pipeline(p) for p in (results if isinstance(results, list) else [])]


@mcp.tool()
def get_mr_discussions(
    project_id: str,
    mr_iid: int,
    page: int = 1,
    per_page: int = 50,
) -> object:
    """
    List discussion threads on an MR (inline + general). Each thread has an id
    (needed for reply_to_mr_discussion) and its notes. System events are stripped.
    """
    results = _get(
        f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/discussions",
        page=page, per_page=per_page,
    )
    return [d for d in [_slim_discussion(r) for r in (results if isinstance(results, list) else [])] if d]


@mcp.tool()
def get_mr_approvals(project_id: str, mr_iid: int) -> dict:
    """Get MR approval status: required count, approved_by list, whether approved."""
    data = _get(f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/approvals")
    return _compact({
        "approvals_required": data.get("approvals_required"),
        "approvals_left": data.get("approvals_left"),
        "approved": data.get("approved"),
        "approved_by": [a["user"]["username"] for a in data.get("approved_by", [])],
        "suggested_approvers": [u["username"] for u in data.get("suggested_approvers", [])],
    })


@mcp.tool()
def get_mr_participants(project_id: str, mr_iid: int) -> object:
    """List all users who participated in an MR (author, commenters, assignees)."""
    results = _get(f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/participants")
    return [_compact({"id": u["id"], "username": u["username"], "name": u["name"]})
            for u in (results if isinstance(results, list) else [])]


@mcp.tool()
def create_mr_note(project_id: str, mr_iid: int, body: str) -> dict:
    """Post a general (non-inline) comment on an MR."""
    n = _post(f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/notes", {"body": body})
    return _slim_note(n)


@mcp.tool()
def reply_to_mr_discussion(
    project_id: str,
    mr_iid: int,
    discussion_id: str,
    body: str,
) -> dict:
    """Reply to an existing MR discussion thread. Get discussion_id from get_mr_discussions."""
    n = _post(
        f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/discussions/{discussion_id}/notes",
        {"body": body},
    )
    return _slim_note(n)


@mcp.tool()
def resolve_mr_discussion(
    project_id: str,
    mr_iid: int,
    discussion_id: str,
    resolved: bool = True,
) -> dict:
    """Resolve or unresolve an MR discussion thread."""
    data = _put(
        f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/discussions/{discussion_id}",
        {"resolved": resolved},
    )
    return _compact({"id": data.get("id"), "resolved": resolved})


@mcp.tool()
def create_mr_inline_note(
    project_id: str,
    mr_iid: int,
    body: str,
    file_path: str,
    base_sha: str,
    start_sha: str,
    head_sha: str,
    new_line: Optional[int] = None,
    old_line: Optional[int] = None,
) -> dict:
    """
    Post an inline diff comment on a specific file/line in an MR.
    Get base_sha, start_sha, head_sha from get_merge_request diff_refs field.
    """
    position = _compact({
        "position_type": "text",
        "base_sha": base_sha,
        "start_sha": start_sha,
        "head_sha": head_sha,
        "new_path": file_path,
        "old_path": file_path,
        "new_line": new_line,
        "old_line": old_line,
    })
    data = _post(
        f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/discussions",
        {"body": body, "position": position},
    )
    return _compact({"id": data.get("id"), "note_id": (data.get("notes") or [{}])[0].get("id")})


# ═══════════════════════════════════════════════════════════════════════════════
# ISSUES  (official plugin parity + extended)
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_issue(id: str, issue_iid: int) -> dict:
    """Get a single project issue."""
    return _slim_issue(_get(f"projects/{_pid(id)}/issues/{issue_iid}"))


@mcp.tool()
def list_project_issues(
    project_id: str,
    state: str = "opened",
    labels: Optional[str] = None,
    author_username: Optional[str] = None,
    assignee_username: Optional[str] = None,
    search: Optional[str] = None,
    order_by: str = "updated_at",
    sort: str = "desc",
    page: int = 1,
    per_page: int = 20,
) -> object:
    """List issues for a project. state: opened|closed|all."""
    results = _get(
        f"projects/{_pid(project_id)}/issues",
        state=state, labels=labels, author_username=author_username,
        assignee_username=assignee_username, search=search,
        order_by=order_by, sort=sort, page=page, per_page=per_page,
    )
    return [_slim_issue(i) for i in (results if isinstance(results, list) else [])]


@mcp.tool()
def create_issue(
    id: str,
    title: str,
    description: Optional[str] = None,
    labels: Optional[str] = None,
    assignee_ids: Optional[list[int]] = None,
    milestone_id: Optional[int] = None,
    confidential: Optional[bool] = None,
) -> dict:
    """Create a new issue in a project."""
    body = _compact({
        "title": title, "description": description, "labels": labels,
        "assignee_ids": assignee_ids, "milestone_id": milestone_id,
        "confidential": confidential,
    })
    return _slim_issue(_post(f"projects/{_pid(id)}/issues", body))


@mcp.tool()
def update_issue(
    project_id: str,
    issue_iid: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    labels: Optional[str] = None,
    add_labels: Optional[str] = None,
    remove_labels: Optional[str] = None,
    assignee_ids: Optional[list[int]] = None,
    state_event: Optional[str] = None,
    milestone_id: Optional[int] = None,
) -> dict:
    """Update an issue. state_event: close|reopen."""
    body = _compact({
        "title": title, "description": description, "labels": labels,
        "add_labels": add_labels, "remove_labels": remove_labels,
        "assignee_ids": assignee_ids, "state_event": state_event,
        "milestone_id": milestone_id,
    })
    return _slim_issue(_put(f"projects/{_pid(project_id)}/issues/{issue_iid}", body))


@mcp.tool()
def get_issue_notes(
    project_id: str,
    issue_iid: int,
    page: int = 1,
    per_page: int = 50,
) -> object:
    """List comments on an issue. System events are stripped."""
    results = _get(
        f"projects/{_pid(project_id)}/issues/{issue_iid}/notes",
        page=page, per_page=per_page, sort="asc",
    )
    return [_slim_note(n) for n in (results if isinstance(results, list) else [])
            if not n.get("system")]


@mcp.tool()
def create_issue_note(project_id: str, issue_iid: int, body: str) -> dict:
    """Post a comment on an issue."""
    n = _post(f"projects/{_pid(project_id)}/issues/{issue_iid}/notes", {"body": body})
    return _slim_note(n)


# ═══════════════════════════════════════════════════════════════════════════════
# WORK ITEMS  (official plugin parity — REST fallback for issues)
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_workitem_notes(
    project_id: Optional[str] = None,
    work_item_iid: Optional[int] = None,
    first: int = 25,
) -> object:
    """
    Get notes for a work item (issue). Equivalent to get_issue_notes.
    Provide project_id + work_item_iid.
    """
    if not project_id or not work_item_iid:
        return {"error": "project_id and work_item_iid are required"}
    results = _get(
        f"projects/{_pid(project_id)}/issues/{work_item_iid}/notes",
        per_page=min(first, 100), sort="asc",
    )
    return [_slim_note(n) for n in (results if isinstance(results, list) else [])
            if not n.get("system")]


@mcp.tool()
def create_workitem_note(
    body: str,
    project_id: Optional[str] = None,
    work_item_iid: Optional[int] = None,
    internal: bool = False,
) -> dict:
    """
    Create a note on a work item (issue). Provide project_id + work_item_iid.
    Set internal=True for internal notes visible only to members with Reporter+.
    """
    if not project_id or not work_item_iid:
        return {"error": "project_id and work_item_iid are required"}
    n = _post(
        f"projects/{_pid(project_id)}/issues/{work_item_iid}/notes",
        {"body": body, "internal": internal},
    )
    return _slim_note(n)


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINES & CI  (official plugin parity + extended)
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def manage_pipeline(
    id: str,
    list: bool = False,
    pipeline_id: Optional[int] = None,
    retry: bool = False,
    cancel: bool = False,
    ref: Optional[str] = None,
    variables: Optional[list] = None,
    page: int = 1,
    per_page: int = 20,
) -> object:
    """
    Manage CI/CD pipelines.
    - list=True: list pipelines (optionally filter by ref)
    - ref provided (no pipeline_id): create/trigger a pipeline on that ref
    - retry=True + pipeline_id: retry a pipeline
    - cancel=True + pipeline_id: cancel a running pipeline
    """
    base = f"projects/{_pid(id)}/pipelines"

    if list:
        results = _get(base, ref=ref, page=page, per_page=per_page)
        return [_slim_pipeline(p) for p in (results if isinstance(results, list) else [])]

    if pipeline_id and retry:
        return _slim_pipeline(_post(f"{base}/{pipeline_id}/retry", {}))

    if pipeline_id and cancel:
        return _slim_pipeline(_post(f"{base}/{pipeline_id}/cancel", {}))

    if ref:
        body: dict = {"ref": ref}
        if variables:
            body["variables"] = variables
        return _slim_pipeline(_post(base, body))

    return {"error": "Provide list=True, ref (to create), or pipeline_id + retry/cancel."}


@mcp.tool()
def list_project_pipelines(
    project_id: str,
    status: Optional[str] = None,
    ref: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> object:
    """List pipelines. status: running|pending|success|failed|canceled|skipped."""
    results = _get(
        f"projects/{_pid(project_id)}/pipelines",
        status=status, ref=ref, page=page, per_page=per_page,
    )
    return [_slim_pipeline(p) for p in (results if isinstance(results, list) else [])]


@mcp.tool()
def get_pipeline_jobs(
    id: str,
    pipeline_id: int,
    page: int = 1,
    per_page: int = 20,
) -> object:
    """List jobs in a pipeline (slimmed: id, name, stage, status, duration, url)."""
    results = _get(
        f"projects/{_pid(id)}/pipelines/{pipeline_id}/jobs",
        page=page, per_page=per_page,
    )
    return [_slim_job(j) for j in (results if isinstance(results, list) else [])]


@mcp.tool()
def get_pipeline_job_log(
    project_id: str,
    job_id: int,
    last_lines: int = 200,
) -> str:
    """Get the last N lines of a job log. Use get_pipeline_jobs to find job_id."""
    log = _text(f"projects/{_pid(project_id)}/jobs/{job_id}/trace")
    lines = log.splitlines()
    if len(lines) > last_lines:
        cut = len(lines) - last_lines
        lines = [f"[...{cut} lines omitted...]"] + lines[-last_lines:]
    return "\n".join(lines)


@mcp.tool()
def retry_job(project_id: str, job_id: int) -> dict:
    """Retry a failed or cancelled job."""
    return _slim_job(_post(f"projects/{_pid(project_id)}/jobs/{job_id}/retry", {}))


@mcp.tool()
def cancel_job(project_id: str, job_id: int) -> dict:
    """Cancel a running job."""
    return _slim_job(_post(f"projects/{_pid(project_id)}/jobs/{job_id}/cancel", {}))


# ═══════════════════════════════════════════════════════════════════════════════
# REPOSITORY
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_file_at_ref(
    project_id: str,
    file_path: str,
    ref: str = "main",
) -> str:
    """Get raw file content at a branch, tag, or commit SHA."""
    enc = quote(file_path, safe="")
    return _text(f"projects/{_pid(project_id)}/repository/files/{enc}/raw?ref={quote(ref, safe='')}")


@mcp.tool()
def list_repository_tree(
    project_id: str,
    path: str = "",
    ref: str = "main",
    recursive: bool = False,
    page: int = 1,
    per_page: int = 50,
) -> object:
    """Browse files and directories at a path in a repository."""
    results = _get(
        f"projects/{_pid(project_id)}/repository/tree",
        path=path or None, ref=ref, recursive=recursive,
        page=page, per_page=per_page,
    )
    return [_compact({"id": e.get("id", "")[:8], "name": e.get("name"),
                       "type": e.get("type"), "path": e.get("path")})
            for e in (results if isinstance(results, list) else [])]


@mcp.tool()
def list_commits(
    project_id: str,
    ref: str = "main",
    path: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> object:
    """List commits on a branch/ref, optionally filtered by file path or date range."""
    results = _get(
        f"projects/{_pid(project_id)}/repository/commits",
        ref_name=ref, path=path, since=since, until=until,
        page=page, per_page=per_page,
    )
    return [_slim_commit(c) for c in (results if isinstance(results, list) else [])]


@mcp.tool()
def compare_refs(
    project_id: str,
    from_ref: str,
    to_ref: str,
    straight: bool = False,
) -> object:
    """
    Compare two branches, tags, or commit SHAs. Returns commits and file diffs.
    straight=True uses direct diff; False (default) uses merge-base diff.
    Diffs truncated at 150 lines per file.
    """
    data = _get(
        f"projects/{_pid(project_id)}/repository/compare",
        from_=from_ref, to=to_ref, straight=straight,
    )
    return _compact({
        "commit_count": len(data.get("commits", [])),
        "commits": [_slim_commit(c) for c in data.get("commits", [])],
        "diffs": [_slim_diff(d) for d in data.get("diffs", [])],
    })


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def list_project_members(
    project_id: str,
    query: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
) -> object:
    """List direct project members with access levels (Guest/Reporter/Developer/Maintainer/Owner)."""
    results = _get(
        f"projects/{_pid(project_id)}/members",
        query=query, page=page, per_page=per_page,
    )
    return [_slim_member(m) for m in (results if isinstance(results, list) else [])]


@mcp.tool()
def list_project_variables(project_id: str) -> object:
    """
    List CI/CD variable keys for a project. Masked/protected values are hidden by GitLab.
    Returns only key, variable_type, protected, masked, environment_scope.
    """
    results = _get(f"projects/{_pid(project_id)}/variables")
    return [_compact({
        "key": v.get("key"),
        "type": v.get("variable_type"),
        "protected": v.get("protected") or None,
        "masked": v.get("masked") or None,
        "environment_scope": v.get("environment_scope") if v.get("environment_scope") != "*" else None,
    }) for v in (results if isinstance(results, list) else [])]


# ═══════════════════════════════════════════════════════════════════════════════
# ISSUE TRACKER  (cross-repo aggregation for Git Issue Tracker reports)
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_all_group_issues(
    group_id: str,
    state: str = "opened",
    labels: Optional[str] = None,
    max_pages: int = 50,
) -> list[dict]:
    """Paginate through ALL issues in a single group (up to max_pages × 100)."""
    issues: list[dict] = []
    for page in range(1, max_pages + 1):
        batch = _get(
            f"groups/{_gid(group_id)}/issues",
            state=state,
            labels=labels,
            per_page=100,
            page=page,
            order_by="created_at",
            sort="desc",
        )
        if not isinstance(batch, list) or not batch:
            break
        issues.extend(batch)
        if len(batch) < 100:
            break
    return issues


def _fetch_all_groups_issues(
    group_ids: list[str],
    state: str = "opened",
    max_pages: int = 50,
) -> list[dict]:
    """Fetch and deduplicate issues across multiple groups."""
    seen: set[str] = set()
    issues: list[dict] = []
    for gid in group_ids:
        for issue in _fetch_all_group_issues(gid, state=state, max_pages=max_pages):
            key = issue.get("web_url") or str(issue.get("id"))
            if key not in seen:
                seen.add(key)
                issues.append(issue)
    return issues


def _priority_from_labels(labels: list[str], priority_labels: list[str]) -> Optional[str]:
    """Return the first matching priority label found in the issue's labels."""
    label_set = {lb.upper() for lb in labels}
    for p in priority_labels:
        if p.upper() in label_set:
            return p.upper()
    return None


def _slim_tracker_issue(issue: dict) -> dict:
    """Slim issue for tracker output: keeps fields needed for the Excel."""
    assignees = issue.get("assignees") or []
    return _compact({
        "iid": issue.get("iid"),
        "title": issue.get("title"),
        "created_at": issue.get("created_at"),
        "labels": issue.get("labels") or [],
        "assignee": assignees[0]["name"] if assignees else None,
        "assignee_username": assignees[0]["username"] if assignees else None,
        "author": (issue.get("author") or {}).get("name"),
        "project_id": issue.get("project_id"),
        "web_url": issue.get("web_url"),
    })


@mcp.tool()
def get_issue_tracker_summary(
    group_ids: list[str],
    priority_labels: list[str] = ["P1", "P2", "P3", "P4", "P5"],
    state: str = "opened",
    max_pages: int = 50,
) -> dict:
    """
    Fetch ALL open issues across every repo in one or more GitLab groups and return:
    - summary: per-assignee counts broken down by priority label
    - by_priority: raw slim issue rows keyed by priority (P1/P2/…)
    - totals: aggregate counts

    Designed for the Git Issue Tracker weekly report. Handles pagination and
    cross-group deduplication internally (up to max_pages × 100 issues per group).

    group_ids: list of group full paths or numeric IDs.
               e.g. ["Backend", "server", "mobile"]
    priority_labels: label names to recognise as priorities (default P1–P5).
    Issues with none of these labels land in by_priority["UNLABELLED"].
    """
    all_issues = _fetch_all_groups_issues(group_ids, state=state, max_pages=max_pages)

    p_upper = [p.upper() for p in priority_labels]

    # Aggregation structures
    assignee_counts: dict[str, dict] = {}  # username -> {name, p1..p5, total}
    by_priority: dict[str, list] = {p: [] for p in p_upper}
    by_priority["UNLABELLED"] = []

    for issue in all_issues:
        slim = _slim_tracker_issue(issue)
        labels = [lb.upper() for lb in (issue.get("labels") or [])]
        priority = _priority_from_labels(labels, p_upper) or "UNLABELLED"

        by_priority[priority].append(slim)

        username = slim.get("assignee_username") or "__unassigned__"
        name = slim.get("assignee") or "Unassigned"

        if username not in assignee_counts:
            assignee_counts[username] = {"name": name, "username": username, "total": 0}
            for p in p_upper:
                assignee_counts[username][p] = 0

        assignee_counts[username]["total"] += 1
        if priority in assignee_counts[username]:
            assignee_counts[username][priority] += 1

    summary = sorted(assignee_counts.values(), key=lambda x: x["total"], reverse=True)

    totals = {"total": len(all_issues)}
    for p in p_upper:
        totals[p] = len(by_priority[p])
    totals["UNLABELLED"] = len(by_priority["UNLABELLED"])

    return _compact({
        "totals": totals,
        "summary": summary,
        "by_priority": by_priority,
    })


@mcp.tool()
def get_manager_team_issues(
    group_ids: list[str],
    manager_name: str,
    assignee_usernames: list[str],
    priority_labels: list[str] = ["P1", "P2", "P3", "P4", "P5"],
    state: str = "opened",
    max_pages: int = 50,
) -> dict:
    """
    Return open issues across one or more GitLab groups filtered to a manager's team.
    Used to generate per-manager Excel files for the Git Issue Tracker report.

    group_ids: list of group full paths or numeric IDs (same as get_issue_tracker_summary)
    manager_name: display name used in the output (e.g. "Ahmad Fatihi")
    assignee_usernames: list of GitLab usernames belonging to this manager's team
    priority_labels: priority labels to recognise (default P1–P5)

    Returns:
    - manager: manager_name
    - summary: per-member counts by priority
    - by_priority: raw slim issue rows keyed by priority
    - totals: aggregate counts for this team
    """
    all_issues = _fetch_all_groups_issues(group_ids, state=state, max_pages=max_pages)

    username_set = {u.lower() for u in assignee_usernames}
    p_upper = [p.upper() for p in priority_labels]

    member_counts: dict[str, dict] = {}
    by_priority: dict[str, list] = {p: [] for p in p_upper}
    by_priority["UNLABELLED"] = []

    for issue in all_issues:
        assignees = issue.get("assignees") or []
        if not assignees:
            continue
        assignee = assignees[0]
        if assignee.get("username", "").lower() not in username_set:
            continue

        slim = _slim_tracker_issue(issue)
        labels = [lb.upper() for lb in (issue.get("labels") or [])]
        priority = _priority_from_labels(labels, p_upper) or "UNLABELLED"

        by_priority[priority].append(slim)

        username = assignee.get("username", "")
        name = assignee.get("name", username)

        if username not in member_counts:
            member_counts[username] = {"name": name, "username": username, "total": 0}
            for p in p_upper:
                member_counts[username][p] = 0

        member_counts[username]["total"] += 1
        if priority in member_counts[username]:
            member_counts[username][priority] += 1

    summary = sorted(member_counts.values(), key=lambda x: x["total"], reverse=True)

    totals = {"total": sum(v["total"] for v in member_counts.values())}
    for p in p_upper:
        totals[p] = len(by_priority[p])

    return _compact({
        "manager": manager_name,
        "totals": totals,
        "summary": summary,
        "by_priority": by_priority,
    })


@mcp.tool()
def get_assignee_priority_counts(
    assignee_usernames: list[str],
    priority_labels: list[str] = ["P1", "P2", "P3", "P4", "P5"],
    state: str = "opened",
    max_pages: int = 20,
) -> dict:
    """
    Query open issues per assignee across ALL accessible projects (instance-wide),
    grouped by priority label. Mirrors the GitLab dashboard work_items view.

    Makes one paginated request per priority label, then aggregates by assignee.
    More efficient than group-level queries when you know the assignee list upfront.

    assignee_usernames: GitLab usernames to include (e.g. ["PuvaanRaaj", "aniq"])
    priority_labels: label names to query (default P1–P5); each becomes a separate request
    state: opened|closed|all

    Returns:
    - summary: [{name, username, P1, P2, P3, P4, P5, total}] sorted by total desc
    - by_priority: {P1: [slim issues], P2: [...], ...}
    - totals: aggregate counts
    """
    username_set = {u.lower() for u in assignee_usernames}
    p_upper = [p.upper() for p in priority_labels]

    by_priority: dict[str, list] = {p: [] for p in p_upper}
    assignee_counts: dict[str, dict] = {}

    for priority in p_upper:
        # Fetch all issues with this priority label, paginated
        issues: list[dict] = []
        for page in range(1, max_pages + 1):
            batch = _get(
                "issues",
                state=state,
                labels=priority,
                per_page=100,
                page=page,
                order_by="created_at",
                sort="desc",
            )
            if not isinstance(batch, list) or not batch:
                break
            issues.extend(batch)
            if len(batch) < 100:
                break

        for issue in issues:
            assignees = issue.get("assignees") or []
            if not assignees:
                continue
            assignee = assignees[0]
            uname = assignee.get("username", "")
            if username_set and uname.lower() not in username_set:
                continue

            slim = _slim_tracker_issue(issue)
            by_priority[priority].append(slim)

            name = assignee.get("name", uname)
            if uname not in assignee_counts:
                assignee_counts[uname] = {"name": name, "username": uname, "total": 0}
                for p in p_upper:
                    assignee_counts[uname][p] = 0

            assignee_counts[uname][priority] += 1
            assignee_counts[uname]["total"] += 1

    summary = sorted(assignee_counts.values(), key=lambda x: x["total"], reverse=True)
    totals = {"total": sum(v["total"] for v in assignee_counts.values())}
    for p in p_upper:
        totals[p] = len(by_priority[p])

    return _compact({
        "totals": totals,
        "summary": summary,
        "by_priority": by_priority,
    })


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not GITLAB_TOKEN:
        print("ERROR: GITLAB_TOKEN is not set.", file=sys.stderr)
        sys.exit(1)
    mcp.run()
