# GitLab Extended MCP

A token-efficient MCP server for Claude Code that replaces and extends the official Claude GitLab plugin.

- **38 tools** vs 14 in the official plugin
- **Slimmed responses** — raw GitLab objects stripped to only useful fields
- **Diffs truncated** at 150 lines per file with a `[...truncated]` marker
- **System notes filtered** from discussions and issue comments
- **Nulls stripped** from every response via `_compact()`

---

## Tools

### Merge Requests
| Tool | Description |
|---|---|
| `get_merge_request` | Single MR — slimmed to ~15 fields including `diff_refs` |
| `list_project_mrs` | List MRs with state / author / label / branch filters |
| `create_merge_request` | Create a new MR |
| `update_mr` | Update title, description, labels, assignees, or state |
| `get_merge_request_diffs` | File diffs, each truncated at 150 lines |
| `get_mr_diff_stats` | Per-file add/remove counts without diff content |
| `get_merge_request_commits` | Commits in an MR (sha, title, author, date) |
| `get_merge_request_conflicts` | Raw git conflict markers for conflicted MRs |
| `get_merge_request_pipelines` | Pipelines triggered for an MR |
| `get_mr_discussions` | Discussion threads with replies — system events stripped |
| `get_mr_approvals` | Approval status, approver list, required count |
| `get_mr_participants` | All users who participated in an MR |
| `create_mr_note` | Post a general comment on an MR |
| `create_mr_inline_note` | Post an inline diff comment at a specific file/line |
| `reply_to_mr_discussion` | Reply to an existing discussion thread |
| `resolve_mr_discussion` | Resolve or unresolve a discussion thread |

### Issues
| Tool | Description |
|---|---|
| `get_issue` | Single issue — slimmed to ~10 fields |
| `list_project_issues` | List issues with state / label / assignee filters |
| `create_issue` | Create a new issue |
| `update_issue` | Update title, labels, assignees, or state |
| `get_issue_notes` | Issue comments — system events stripped |
| `create_issue_note` | Post a comment on an issue |

### Work Items (official plugin parity)
| Tool | Description |
|---|---|
| `get_workitem_notes` | Notes for a work item (issue) |
| `create_workitem_note` | Create a note on a work item |

### Pipelines & CI
| Tool | Description |
|---|---|
| `manage_pipeline` | List / create / retry / cancel pipelines |
| `list_project_pipelines` | List pipelines with status and ref filters |
| `get_pipeline_jobs` | Jobs in a pipeline (id, name, stage, status, duration) |
| `get_pipeline_job_log` | Last N lines of a job log |
| `retry_job` | Retry a failed or cancelled job |
| `cancel_job` | Cancel a running job |

### Repository
| Tool | Description |
|---|---|
| `get_file_at_ref` | Raw file content at a branch, tag, or commit SHA |
| `list_repository_tree` | Browse files and directories at a path |
| `list_commits` | Commit history for a branch, optionally filtered by path |
| `compare_refs` | Diff between two branches or SHAs |

### Project & Search
| Tool | Description |
|---|---|
| `get_project` | Project metadata (default branch, visibility, open issues) |
| `search` | Search issues, MRs, blobs, commits, notes, users |
| `search_labels` | Search labels in a project or group |
| `list_project_labels` | List all labels for a project |
| `list_project_members` | Members with access levels |
| `list_project_variables` | CI/CD variable keys (masked values hidden by GitLab) |

---

## Setup

### Option A — Docker (recommended)

Pull the pre-built multi-arch image (amd64 + arm64):

```bash
docker pull YOUR_DOCKERHUB_USERNAME/gitlab-extended-mcp:latest
```

Register with Claude Code:

```bash
claude mcp add gitlab-extended \
  --scope user \
  -- docker run --rm -i \
  -e GITLAB_URL=https://gitlab.example.com \
  -e GITLAB_TOKEN=glpat-your-token \
  YOUR_DOCKERHUB_USERNAME/gitlab-extended-mcp:latest
```

### Option B — Build locally

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/gitlab-extended-mcp.git
cd gitlab-extended-mcp
docker build -t gitlab-extended-mcp .

claude mcp add gitlab-extended \
  --scope user \
  -- docker run --rm -i \
  -e GITLAB_URL=https://gitlab.example.com \
  -e GITLAB_TOKEN=glpat-your-token \
  gitlab-extended-mcp
```

### Option C — Python directly

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

GITLAB_URL=https://gitlab.example.com \
GITLAB_TOKEN=glpat-your-token \
python server.py
```

Register with Claude Code:

```bash
claude mcp add gitlab-extended \
  -e GITLAB_URL=https://gitlab.example.com \
  -e GITLAB_TOKEN=glpat-your-token \
  --scope user \
  -- /path/to/.venv/bin/python /path/to/server.py
```

---

## Auth

Requires a GitLab Personal Access Token with `api` scope.

GitLab → User Settings → Access Tokens → New token → select `api`.

---

## Token efficiency

| | Official plugin | This server |
|---|---|---|
| MR object fields | ~50 | ~15 |
| Diff lines per file | Unlimited | Capped at 150 |
| System notes | Included | Stripped |
| Null fields | Included | Stripped |
| Commit SHA | 40 chars | 8 chars |
| User objects | Full (8+ fields) | `username` only |

Typical MR review workflow uses **40–60% fewer tokens** compared to the official plugin.

