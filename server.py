#!/usr/bin/env python3
"""
GitLab Extended MCP Server

Provides GitLab API tools missing from the official Claude GitLab plugin.
Authenticates with the same GITLAB_TOKEN and GITLAB_URL used by the plugin.

Missing tools covered here:
  - get_mr_discussions     : list all discussion threads (with replies) on an MR
  - reply_to_mr_discussion : post a reply to an existing thread
  - create_mr_note         : create a new general MR comment
  - resolve_mr_discussion  : resolve or unresolve a discussion thread
  - get_mr_approvals       : get MR approval status and approver list
  - list_project_mrs       : list MRs with filters (state, author, labels, etc.)
  - update_mr              : update MR title, description, labels, or assignees
  - get_pipeline_job_log   : stream the last N lines of a pipeline job log
  - get_file_at_ref        : get file content at a specific branch or commit SHA
  - list_project_members   : list project members with their access levels
  - create_mr_inline_note  : post an inline diff comment at a specific file/line
"""

from __future__ import annotations

import os
import textwrap
from typing import Optional
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP

# ── Auth & base URL ───────────────────────────────────────────────────────────
GITLAB_URL: str = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
GITLAB_TOKEN: str = os.environ.get("GITLAB_TOKEN", "")

mcp = FastMCP(
    "gitlab-extended",
    instructions=(
        "Extended GitLab tools covering MR discussions, replies, approvals, "
        "pipeline job logs, file content, and project membership — capabilities "
        "not provided by the official GitLab Claude plugin."
    ),
)


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _api(path: str) -> str:
    return f"{GITLAB_URL}/api/v4/{path.lstrip('/')}"


def _headers() -> dict[str, str]:
    return {"PRIVATE-TOKEN": GITLAB_TOKEN}


def _pid(project_id: str) -> str:
    """URL-encode a project path like 'group/repo' for use in API paths."""
    return quote(project_id, safe="")


def _get(path: str, **params) -> object:
    with httpx.Client(timeout=30) as client:
        r = client.get(_api(path), headers=_headers(), params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()


def _post(path: str, body: dict) -> object:
    with httpx.Client(timeout=30) as client:
        r = client.post(_api(path), headers=_headers(), json=body)
        r.raise_for_status()
        return r.json()


def _put(path: str, body: dict) -> object:
    with httpx.Client(timeout=30) as client:
        r = client.put(_api(path), headers=_headers(), json=body)
        r.raise_for_status()
        return r.json()


def _get_text(path: str) -> str:
    with httpx.Client(timeout=60) as client:
        r = client.get(_api(path), headers=_headers())
        r.raise_for_status()
        return r.text


# ── Tools ─────────────────────────────────────────────────────────────────────


@mcp.tool()
def get_mr_discussions(
    project_id: str,
    mr_iid: int,
    page: int = 1,
    per_page: int = 50,
) -> object:
    """
    Get all discussion threads on a merge request, including inline diff threads
    and general comment threads. Each thread contains its notes (replies) in order.

    Args:
        project_id: Project ID (numeric) or URL-encoded path (e.g. 'group/repo').
        mr_iid:     Internal MR ID shown in the GitLab UI (e.g. 1 for !1).
        page:       Page number for pagination (default 1).
        per_page:   Results per page, max 100 (default 50).

    Returns:
        List of discussion objects. Each has:
          - id: discussion thread ID (needed for replies)
          - notes[]: list of note objects (author, body, position, resolved, etc.)
    """
    return _get(
        f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/discussions",
        page=page,
        per_page=per_page,
    )


@mcp.tool()
def reply_to_mr_discussion(
    project_id: str,
    mr_iid: int,
    discussion_id: str,
    body: str,
) -> object:
    """
    Post a reply to an existing MR discussion thread.

    Args:
        project_id:    Project ID or path.
        mr_iid:        Internal MR ID.
        discussion_id: The discussion thread ID (from get_mr_discussions).
        body:          Markdown text of the reply.

    Returns:
        The created note object.
    """
    return _post(
        f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/discussions/{discussion_id}/notes",
        {"body": body},
    )


@mcp.tool()
def create_mr_note(
    project_id: str,
    mr_iid: int,
    body: str,
) -> object:
    """
    Create a new general (non-diff) comment on a merge request.

    Args:
        project_id: Project ID or path.
        mr_iid:     Internal MR ID.
        body:       Markdown text of the comment.

    Returns:
        The created note object with its ID.
    """
    return _post(
        f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/notes",
        {"body": body},
    )


@mcp.tool()
def resolve_mr_discussion(
    project_id: str,
    mr_iid: int,
    discussion_id: str,
    resolved: bool = True,
) -> object:
    """
    Resolve or unresolve a merge request discussion thread.

    Args:
        project_id:    Project ID or path.
        mr_iid:        Internal MR ID.
        discussion_id: The discussion thread ID (from get_mr_discussions).
        resolved:      True to resolve, False to unresolve (default True).

    Returns:
        The updated discussion object.
    """
    return _put(
        f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/discussions/{discussion_id}",
        {"resolved": resolved},
    )


@mcp.tool()
def get_mr_approvals(
    project_id: str,
    mr_iid: int,
) -> object:
    """
    Get the approval state of a merge request, including who has approved,
    how many approvals are required, and whether it is approved.

    Args:
        project_id: Project ID or path.
        mr_iid:     Internal MR ID.

    Returns:
        Approval state object with fields:
          - approvals_required, approvals_left, approved
          - approved_by[]: list of users who have approved
          - suggested_approvers[]: list of suggested approvers
    """
    return _get(
        f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/approvals",
    )


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
    """
    List merge requests for a project with filtering and sorting.

    Args:
        project_id:      Project ID or path.
        state:           Filter by state: 'opened', 'closed', 'merged', 'all' (default 'opened').
        author_username: Filter by author username.
        labels:          Comma-separated label names to filter by.
        target_branch:   Filter by target branch name.
        source_branch:   Filter by source branch name.
        search:          Search in title and description.
        order_by:        Order by 'created_at' or 'updated_at' (default 'updated_at').
        sort:            'asc' or 'desc' (default 'desc').
        page:            Page number (default 1).
        per_page:        Results per page, max 100 (default 20).

    Returns:
        List of MR objects with iid, title, state, author, labels, web_url, etc.
    """
    return _get(
        f"projects/{_pid(project_id)}/merge_requests",
        state=state,
        author_username=author_username,
        labels=labels,
        target_branch=target_branch,
        source_branch=source_branch,
        search=search,
        order_by=order_by,
        sort=sort,
        page=page,
        per_page=per_page,
    )


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
) -> object:
    """
    Update fields on an existing merge request.

    Args:
        project_id:    Project ID or path.
        mr_iid:        Internal MR ID.
        title:         New title.
        description:   New description (Markdown).
        labels:        Replace all labels with this comma-separated list.
        add_labels:    Comma-separated labels to add without replacing others.
        remove_labels: Comma-separated labels to remove.
        assignee_ids:  List of user IDs to assign (empty list to unassign all).
        reviewer_ids:  List of user IDs to set as reviewers.
        target_branch: Change the target branch.
        state_event:   'close' to close the MR, 'reopen' to reopen it.

    Returns:
        The updated MR object.
    """
    body: dict = {}
    if title is not None:
        body["title"] = title
    if description is not None:
        body["description"] = description
    if labels is not None:
        body["labels"] = labels
    if add_labels is not None:
        body["add_labels"] = add_labels
    if remove_labels is not None:
        body["remove_labels"] = remove_labels
    if assignee_ids is not None:
        body["assignee_ids"] = assignee_ids
    if reviewer_ids is not None:
        body["reviewer_ids"] = reviewer_ids
    if target_branch is not None:
        body["target_branch"] = target_branch
    if state_event is not None:
        body["state_event"] = state_event

    return _put(
        f"projects/{_pid(project_id)}/merge_requests/{mr_iid}",
        body,
    )


@mcp.tool()
def get_pipeline_job_log(
    project_id: str,
    job_id: int,
    last_lines: int = 200,
) -> str:
    """
    Get the raw log output of a pipeline job, truncated to the last N lines.
    Useful for debugging failed CI steps without reading the full log.

    Args:
        project_id: Project ID or path.
        job_id:     The numeric job ID (from get_pipeline_jobs).
        last_lines: Number of lines to return from the end of the log (default 200).

    Returns:
        Plain text log output (last N lines).
    """
    log = _get_text(f"projects/{_pid(project_id)}/jobs/{job_id}/trace")
    lines = log.splitlines()
    if len(lines) > last_lines:
        truncated = len(lines) - last_lines
        lines = [f"[... {truncated} lines truncated ...]"] + lines[-last_lines:]
    return "\n".join(lines)


@mcp.tool()
def get_file_at_ref(
    project_id: str,
    file_path: str,
    ref: str = "main",
) -> str:
    """
    Get the raw content of a file at a specific branch, tag, or commit SHA.

    Args:
        project_id: Project ID or path.
        file_path:  Path to the file within the repository (e.g. 'src/app.py').
        ref:        Branch name, tag, or commit SHA (default 'main').

    Returns:
        The raw file content as a string.
    """
    encoded_path = quote(file_path, safe="")
    return _get_text(
        f"projects/{_pid(project_id)}/repository/files/{encoded_path}/raw?ref={quote(ref, safe='')}",
    )


@mcp.tool()
def list_project_members(
    project_id: str,
    query: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
) -> object:
    """
    List direct members of a project with their access levels.

    Access levels: 10=Guest, 20=Reporter, 30=Developer, 40=Maintainer, 50=Owner.

    Args:
        project_id: Project ID or path.
        query:      Filter members by name or username (optional).
        page:       Page number (default 1).
        per_page:   Results per page, max 100 (default 50).

    Returns:
        List of member objects with id, username, name, access_level, web_url.
    """
    return _get(
        f"projects/{_pid(project_id)}/members",
        query=query,
        page=page,
        per_page=per_page,
    )


@mcp.tool()
def create_mr_inline_note(
    project_id: str,
    mr_iid: int,
    body: str,
    file_path: str,
    new_line: Optional[int] = None,
    old_line: Optional[int] = None,
    base_sha: str = "",
    start_sha: str = "",
    head_sha: str = "",
) -> object:
    """
    Post an inline diff comment on a specific file and line in a merge request.
    Use get_merge_request (from the main plugin) to get base_sha, start_sha, head_sha
    from the diff_refs field.

    Args:
        project_id: Project ID or path.
        mr_iid:     Internal MR ID.
        body:       Markdown text of the comment.
        file_path:  Path to the file being commented on (e.g. 'src/app.py').
        new_line:   Line number in the new (right-hand) version of the file.
        old_line:   Line number in the old (left-hand) version of the file.
        base_sha:   base_sha from the MR's diff_refs.
        start_sha:  start_sha from the MR's diff_refs.
        head_sha:   head_sha from the MR's diff_refs.

    Returns:
        The created discussion object (thread ID usable for follow-up replies).
    """
    position: dict = {
        "position_type": "text",
        "base_sha": base_sha,
        "start_sha": start_sha,
        "head_sha": head_sha,
        "new_path": file_path,
        "old_path": file_path,
    }
    if new_line is not None:
        position["new_line"] = new_line
    if old_line is not None:
        position["old_line"] = old_line

    return _post(
        f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/discussions",
        {"body": body, "position": position},
    )


@mcp.tool()
def get_mr_diff_stats(
    project_id: str,
    mr_iid: int,
) -> object:
    """
    Get the per-file diff statistics for a merge request (additions, deletions,
    file names) without returning the full diff content. Useful for a quick
    impact overview before fetching the full diffs.

    Args:
        project_id: Project ID or path.
        mr_iid:     Internal MR ID.

    Returns:
        List of objects with old_path, new_path, added_lines, removed_lines,
        new_file, deleted_file, renamed_file.
    """
    changes = _get(
        f"projects/{_pid(project_id)}/merge_requests/{mr_iid}/changes",
    )
    diffs = changes.get("changes", []) if isinstance(changes, dict) else []
    return [
        {
            "old_path": d.get("old_path"),
            "new_path": d.get("new_path"),
            "new_file": d.get("new_file"),
            "deleted_file": d.get("deleted_file"),
            "renamed_file": d.get("renamed_file"),
            "added_lines": d.get("diff", "").count("\n+") if d.get("diff") else 0,
            "removed_lines": d.get("diff", "").count("\n-") if d.get("diff") else 0,
        }
        for d in diffs
    ]


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if not GITLAB_TOKEN:
        print("ERROR: GITLAB_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    mcp.run()
