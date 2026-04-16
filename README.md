# GitLab Extended MCP

An MCP server that extends the official Claude GitLab plugin with tools not yet supported by it. Uses the same `GITLAB_URL` and `GITLAB_TOKEN` environment variables.

## Tools

| Tool | Description |
|---|---|
| `get_mr_discussions` | List all discussion threads (with replies) on an MR |
| `reply_to_mr_discussion` | Post a reply to an existing thread |
| `create_mr_note` | Create a new general MR comment |
| `resolve_mr_discussion` | Resolve or unresolve a discussion thread |
| `get_mr_approvals` | Get approval status and approver list |
| `list_project_mrs` | List MRs with filters (state, author, labels, branch) |
| `update_mr` | Update title, description, labels, assignees, or state |
| `get_pipeline_job_log` | Get last N lines of a pipeline job log |
| `get_file_at_ref` | Get file content at a branch, tag, or commit SHA |
| `list_project_members` | List project members with access levels |
| `create_mr_inline_note` | Post an inline diff comment at a specific file/line |
| `get_mr_diff_stats` | Get per-file diff stats without the full diff content |

## Setup

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your GitLab URL and personal access token
```

The token needs at minimum `api` scope.

### 2. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Or with `uv`:

```bash
uv venv && uv pip install -e .
```

### 3. Add to Claude Code

Add this to `~/.claude/settings.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "gitlab-extended": {
      "command": "/Users/puvaan.shankar/programming/gitlab-extended-mcp/.venv/bin/python",
      "args": ["/Users/puvaan.shankar/programming/gitlab-extended-mcp/server.py"],
      "env": {
        "GITLAB_URL": "https://git2u.fiuu.com",
        "GITLAB_TOKEN": "glpat-your-token-here"
      }
    }
  }
}
```

### 4. Test

```bash
GITLAB_URL=https://git2u.fiuu.com GITLAB_TOKEN=glpat-... python server.py
```

## Auth

Uses a GitLab Personal Access Token (`api` scope). This is the same credential as the official Claude GitLab plugin — you can reference the same token in both.

To create one: GitLab → User Settings → Access Tokens → add `api` scope.
