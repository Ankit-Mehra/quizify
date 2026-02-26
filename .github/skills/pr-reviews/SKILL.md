---
name: pr-reviews
description: Guide for handling Copilot PR reviews and debugging failing GitHub Actions workflows. Use this when asked to check PR reviews, act on Copilot feedback, or debug failing CI workflows.
---

# PR Review & CI Workflow Guide

## Part 1: Copilot Review Cycle

Pull, analyze, and act on GitHub Copilot review feedback for the current PR. Use **GitHub MCP tools** (preferred) or **GitHub CLI** as a fallback.

### Step 1: Identify the PR

**MCP:**
- Use `mcp_github_search_pull_requests` with the current branch name to find the open PR, or use `github-pull-request_activePullRequest` tool to get the currently checked-out PR.

**CLI:**
```bash
gh pr view --json number,title,state,url
```

### Step 2: Check for Existing Reviews

Before requesting a new review, check if Copilot has already reviewed the PR and whether those reviews are still relevant to the current HEAD commit.

**MCP:**
- Activate `activate_github_pull_request_management` tools.
- Use `github-pull-request_activePullRequest` with fields: reviews, review comments.
- This returns all reviews (state, author, body) and inline review comments (path, line, body, diff context).

**CLI:**
```bash
# List all reviews on the PR
gh pr review --list

# Get detailed review comments with file paths and line numbers
gh api repos/{owner}/{repo}/pulls/{pr_number}/comments --jq '.[] | {user: .user.login, path: .path, line: .line, body: .body, created_at: .created_at}'

# Get review summaries
gh api repos/{owner}/{repo}/pulls/{pr_number}/reviews --jq '.[] | {user: .user.login, state: .state, body: .body, submitted_at: .submitted_at}'
```

### Step 3: Request Copilot Review (if needed)

Only request a new review if: (a) no reviews exist yet, or (b) new commits were pushed after the last review.

**MCP:**
- Use `mcp_github_request_copilot_review` with owner, repo, and pullNumber.

**CLI:**
```bash
gh pr edit {pr_number} --add-reviewer "github/copilot"
```

### Step 4: Read & Categorize All Review Comments

Once a review exists, fetch and carefully read every comment. Categorize each:

- 🔴 **Critical** — Security vulnerabilities, bugs, breaking changes → **MUST fix**
- 🟡 **Important** — Performance, maintainability, best practices → **SHOULD fix**
- 🟢 **Nice-to-have** — Style preferences, minor optimizations → **Consider fixing**

**MCP:**
- Use `github-pull-request_activePullRequest` to get review comments with full context (file path, line number, diff hunk, suggestion body).
- Alternatively use `activate_github_pull_request_management` → `github-pull-request_openPullRequest` if viewing a PR that isn't checked out.

**CLI:**
```bash
# Get all review comments with context
gh api repos/{owner}/{repo}/pulls/{pr_number}/comments \
  --jq '.[] | "[\(.user.login)] \(.path):\(.line)\n\(.body)\n---"'

# Get the review-level body comments (not inline)
gh api repos/{owner}/{repo}/pulls/{pr_number}/reviews \
  --jq '.[] | select(.body != "") | "[\(.user.login) - \(.state)]\n\(.body)\n---"'
```

### Step 5: Implement Fixes

For each applicable comment:

1. Read the referenced file and line to understand the full context
2. Implement the suggested fix (or an equivalent improvement)
3. Add explanatory comments if the fix involves non-obvious logic
4. Update tests if behavior changes
5. Run the self-review checklist (type safety, error handling, performance, etc.)

### Step 5b: Reply to Review Comments

After implementing a fix (or deciding a comment doesn't apply), reply directly to the review comment to document the resolution. This creates a clear audit trail on the PR.

**MCP:**
- Use `activate_comment_management_tools` to access the "Add issue comment" tool for general PR-level replies.
- For inline review comment replies, use the GitHub CLI (see below) — MCP doesn't currently support replying to a specific review comment thread.

**CLI:**
```bash
# List review comments with their IDs to find the one to reply to
gh api repos/{owner}/{repo}/pulls/{pr_number}/comments \
  --jq '.[] | {id: .id, user: .user.login, path: .path, line: .line, body: .body}'

# Reply to a specific comment (fixed)
gh api repos/{owner}/{repo}/pulls/{pr_number}/comments/{comment_id}/replies \
  -f body="Fixed in latest commit — [description of what was changed]"

# Reply to a comment (not applicable / intentionally skipped)
gh api repos/{owner}/{repo}/pulls/{pr_number}/comments/{comment_id}/replies \
  -f body="Not applicable — [reason why this suggestion was skipped]"
```

**Reply templates:**
- ✅ Fixed: `"Fixed in [commit_sha] — [brief description]"`
- ⏭️ Not needed: `"Not applicable — [reason, e.g. 'prop is already validated by parent component']"`
- 📌 Deferred: `"Tracked for follow-up — [link to issue or explanation]"`

### Step 6: Commit, Push & Re-request Review

```bash
git add -A
git commit -m "fix: address Copilot review feedback

- [Specific change 1]
- [Specific change 2]"
git push origin {branch-name}
```

Then re-request Copilot review:

**MCP:** `mcp_github_request_copilot_review`
**CLI:** `gh pr edit {pr_number} --add-reviewer "github/copilot"`

### Step 7: Repeat Until Clean

- **Minimum 3 iterations** of Steps 2–6
- Continue until Copilot has no more critical/important feedback
- Document in the PR if a suggestion is intentionally not applied (with justification)

---

## Part 2: Debugging Failing CI Workflows

When GitHub Actions workflows fail on a PR, follow this process:

### Using MCP Tools

1. Use `list_workflow_runs` to look up recent workflow runs for the PR and their status
2. Use `summarize_job_log_failures` to get an AI summary of the logs for failed jobs, to understand what went wrong without filling context windows with thousands of lines of logs
3. If more detail is needed, use `get_job_logs` or `get_workflow_run_logs` for full failure logs

### Using CLI

```bash
# List workflow runs for the current PR
gh run list --branch {branch-name}

# View a specific failed run
gh run view {run-id}

# Get logs for a failed run
gh run view {run-id} --log-failed
```

### Fix the Failure

4. Try to reproduce the failure locally (e.g., `npm run build`, `npm run lint`, `npm test`)
5. Fix the issue and verify the fix locally before committing
6. Commit, push, and confirm the CI workflow passes on the next run
