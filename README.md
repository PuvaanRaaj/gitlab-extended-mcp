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
| `create_project` | Create a new project (visibility, namespace, README init) |
| `search` | Search issues, MRs, blobs, commits, notes, users |
| `search_labels` | Search labels in a project or group |
| `list_project_labels` | List all labels for a project |
| `list_project_members` | Members with access levels |
| `list_project_variables` | CI/CD variable keys (masked values hidden by GitLab) |

---

## Setup

### Option A — Docker Compose, single shared server (recommended)

One persistent container serves all clients (Claude Code, Codex CLI, Claude Desktop, Codex desktop) over HTTP instead of each client spawning its own container.

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/gitlab-extended-mcp.git
cd gitlab-extended-mcp
cp .env.example .env        # then edit .env with your GITLAB_URL + GITLAB_TOKEN

Two tokens: `GITLAB_TOKEN` is the bot account and is used **only** by `create_merge_request`, so MRs are owned by the bot. `GITLAB_USER_TOKEN` is your personal token and is used for everything else (notes, threads, labels, issues, pipelines, reads) so activity is attributed to you. If `GITLAB_USER_TOKEN` is unset, everything falls back to `GITLAB_TOKEN`.
docker compose up -d
```

`docker compose` auto-loads `.env` (gitignored), so secrets stay out of your shell history. You can also pass them inline instead: `GITLAB_URL=... GITLAB_TOKEN=... docker compose up -d`.

Verify it's up: `curl -s http://127.0.0.1:8765/mcp` (a 401/406 response is fine — it proves the endpoint is live).

**Recreating the container:**

```bash
docker compose up -d              # config-only change (mount / env / port)
docker compose up -d --build      # after editing server.py or Dockerfile
docker compose down && docker compose up -d   # full clean restart
```

Register with Claude Code:

```bash
claude mcp add --transport http gitlab-extended http://127.0.0.1:8765/mcp --scope user
```

Register with Codex CLI (Codex desktop shares the same `~/.codex/config.toml`, no separate step needed):

```bash
codex mcp add gitlab-extended --url http://127.0.0.1:8765/mcp
```

Register with Claude Desktop: Settings → Connectors → Add custom connector → `http://127.0.0.1:8765/mcp`. If the Connectors UI rejects a local `http://` URL, fall back to a stdio↔HTTP bridge in `claude_desktop_config.json`:

```json
{"mcpServers":{"gitlab-extended":{"command":"npx","args":["-y","mcp-remote","http://127.0.0.1:8765/mcp"]}}}
```

### Option B — Python directly

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

GITLAB_URL=https://gitlab.example.com \
GITLAB_TOKEN=glpat-your-token \
python server.py
```

Register with Codex:

```bash
codex mcp add gitlab-extended \
  --env GITLAB_URL=https://gitlab.example.com \
  --env GITLAB_TOKEN=glpat-your-token \
  -- /path/to/.venv/bin/python /path/to/server.py
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

## File attachments (Docker Compose)

The `upload_project_attachment` and `append_mr_description_attachment` tools read a local file off disk. In the Compose setup the container only mounts a single dedicated folder, `~/gitlab-mcp-uploads` (read-only) — **not** your whole home or `~/work` tree (mounting a large tree makes Docker's VirtioFS track hundreds of thousands of files and drain the host).

Create the folder once (`mkdir -p ~/gitlab-mcp-uploads`) before the first `docker compose up` — otherwise Docker creates it root-owned. Drop the file into `~/gitlab-mcp-uploads/`, then pass that path to the tool. To use a different folder, edit the `volumes:` entry in `docker-compose.yml` and `docker compose up -d`.

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
