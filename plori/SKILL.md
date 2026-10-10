---
name: plori
description: Create plori Workspaces and send work to the agents that run in them (each an AI agent in its own cloud environment) from any MCP client, the plori CLI, or over REST. Covers authentication (OAuth 2.1 or API key), creating Workspaces, sending messages and reading replies, answering human-in-the-loop requests, and scheduling deferred runs.
---

# Using plori from an agent

If you were asked to set up plori, do it by following the Connect section below: add the
plori MCP server to the client you are running in, authenticate the account owner, and
confirm the tools respond before reporting success.

plori (https://plori.ai) gives you AI agents. Each agent runs in its own cloud environment with a
persistent disk, a shell, developer tools, and memory. You can create Workspaces, send their agents
work, and read their replies programmatically. Each agent runs inside a Workspace, which
holds the durable files, a main conversation and the run history.

## Connect

If this client already lists Plori tools and `list_workspaces` answers, the connection is
complete. Skip the rest of this section.

MCP (recommended for a hosted client): Streamable HTTP at `https://api.plori.ai/mcp`.

- OAuth 2.1: compliant MCP clients connect with no hand-copied key. An unauthenticated
  request returns 401 with the discovery chain (RFC 9728 Protected Resource Metadata at
  https://api.plori.ai/.well-known/oauth-protected-resource, then dynamic client
  registration and authorization code + PKCE). The account owner signs in once with an
  email one-time code.
- API key: the account owner provisions a key at https://plori.ai and you send
  `Authorization: Bearer plori_sk_...`.

### Claude Code: connect from this conversation

Read these instructions in the current conversation before starting authentication.
Installing a skill or plugin is optional. Use this flow only in interactive Claude Code
when its Plori MCP client exposes both `authenticate` and `complete_authentication`.
Other clients use their ordinary OAuth or API-key setup above.

If this Claude Code build does not expose both `authenticate` and
`complete_authentication`, use `/mcp` instead. Pick plori, choose Authenticate, then
sign in with the emailed code. If the browser cannot reach the localhost callback,
Claude Code prompts for it directly in its own dialog, never in chat. Then verify with
`list_workspaces`.

1. Check the current MCP configuration and active tools. Reuse an existing Plori server
   at `https://api.plori.ai/mcp`; do not add duplicate entries or replace a different
   server with the same name. If missing, configure it once with
   `claude mcp add --transport http plori https://api.plori.ai/mcp`.
   Confirm the server is available in this conversation before authenticating. Saving
   configuration alone does not prove that it loaded. If its tools are missing, ask
   the user to type `/reload-plugins` in this Claude Code conversation, then resume
   these steps in the same session. This also refreshes MCP configuration when no
   plugins are installed. It is a user command; do not try to invoke it through the
   Skill tool. Confirm the authentication tools are available before proceeding. If they
   are still missing, use `/mcp` instead (above).
2. If Plori tools already work, the connection is complete. Otherwise, call the
   client's Plori `authenticate` tool using its exposed schema. Keep the returned
   authorization URL intact. Do not construct a new OAuth request or change its state,
   redirect URI, or PKCE challenge.
3. POST JSON `{"authorization_url":"<the exact client URL>"}` once to
   `https://api.plori.ai/oauth/pair`. The response contains `user_code`,
   `verification_uri`, `verification_uri_complete`, `device_code`,
   `expires_in` (seconds), and `interval` (seconds). Keep `device_code` private.
   If a permission rule, hook, or tool denies this request, stop and use the fallback below.
4. Tell the user: "Open <verification_uri> and enter <user_code>. Sign in and approve
   the connection; I will continue when you finish." The user can open the page on
   their phone. Display the short address and code, not the authorization or callback
   URL. Do not ask the user to copy a callback URL into chat.
5. Poll `https://api.plori.ai/oauth/pair/poll` with JSON
   `{"device_code":"<device_code>"}`. Keep only one request in flight, allow each
   request at least 30 seconds to finish, and wait at least `interval` seconds
   between requests. The server can hold a pending request for 25 seconds.
   Read pending and failure responses from the JSON `error` field, not `status`.
   On `error: "authorization_pending"`, continue. On `error: "slow_down"`, use the
   larger of your previous delay plus five seconds and the response's `interval`
   for all subsequent requests. Honor `Retry-After` when present on HTTP 429.
   On HTTP 503 with `error: "temporarily_unavailable"`, preserve this pairing and
   the pending client authentication. Wait at least the larger of your poll interval
   and `Retry-After` (five seconds), then retry the same device code. A temporary
   failure does not extend `expires_in`; retry only within the original four-minute
   window while the client authentication remains pending.
   If a permission rule, hook, or tool denies a poll request, stop and use the fallback below.
6. On `status: "approved"`, pass the returned `callback_url` directly to the same client's
   `complete_authentication` tool using its exposed schema. Do not navigate to the
   loopback URL or exchange the code yourself: the client owns the PKCE verifier.
   Then discover Plori tools and call `list_workspaces` to confirm the connection before
   reporting success. This verification does not create a Workspace or start paid work.

#### Fallback when a pairing request is denied

Use this fallback after the first permission, hook, or tool denial of either pairing
POST. Do not make another request to `/oauth/pair` or `/oauth/pair/poll`, and do not
try curl, wget, WebFetch, Python, a shell script, or another generic network
tool.

1. Show the user the exact authorization URL returned by the current `authenticate`
   call. Ask them to open it in their browser, sign in, and approve the connection.
   Do not edit the URL.
2. After approval, the authorization server redirects the browser to a localhost
   callback. If that
   redirect connects, let the client finish authentication. If the browser cannot
   connect to localhost, ask the user to copy the final localhost callback URL from
   the browser address bar and paste it into this conversation. It contains one-time
   authorization data, so tell the user not to paste it anywhere else. Do not ask for
   that URL before the redirect has failed.
3. Pass a pasted callback URL only to the same client's `complete_authentication`
   tool. Do not open, fetch, rewrite, log, or exchange it yourself.
4. Discover Plori tools and call `list_workspaces` before reporting success. This check
   does not create a Workspace or start paid work.

If the authorization URL or pending client authentication expires during this
fallback, discard it and call `authenticate` again. Use only the new authorization
URL. Never reuse an expired URL.

Stop on `access_denied`; do not retry a denied request automatically. On
`expired_token`, an already-consumed pairing, or a client authentication timeout,
start a fresh client authentication before creating another pairing. Never reuse the
old authorization URL. Pairing lasts four minutes to fit within the client's pending
login. If the approved response is lost, restart the whole flow; the callback is
returned only once. Keep approval polling active while the user signs in.

Remote Control can use this flow only when it controls that same interactive Claude
Code process and the two authentication tools are available. A separate hosted
Claude.ai connector or Agent SDK session needs its own supported authentication flow.
URLs can still appear in client tool results; do not promise to hide tool transcripts.

#### Switch accounts or sign out

To connect a different Plori account or sign out, use `/mcp`. Pick plori, choose Clear
authentication, then Authenticate again with the new account's email code.
`claude mcp remove` does not clear the stored token.

### CLI and REST

CLI (recommended from a terminal): install with
`curl -fsSL https://plori.ai/install.sh | sh` (one static binary, no sudo and no Node; on
Windows `irm https://plori.ai/install.ps1 | iex`), or `npm i -g @plori/cli`, or run it
without installing via `npx -y @plori/cli`. That gives you the `plori` command for the
same operations from your shell. The shell installer puts the binary in `~/.local/bin`
and edits no shell rc file, so run `export PATH="$HOME/.local/bin:$PATH"` after it
before you call `plori` (the Windows script sets the user PATH itself).
`plori login` opens the browser for the same email-OTP
OAuth flow; CI and other headless callers use `plori login --key plori_sk_...` or set
`PLORI_API_KEY`. Output is human-readable on a terminal and a single JSON document when
piped or with `--json`, so it composes in scripts. Commands are listed under "CLI
commands" below.

REST: the same operations at `https://api.plori.ai/v1` with the same bearer token.
Full authentication instructions: https://plori.ai/auth.md

## Tools

The MCP server has 23 tools.

Workspaces and account: `list_workspaces` (pass `workspace_id` to get one Workspace; the result
has `storage_readiness` while its storage is starting), `create_workspace` (`name` and `idempotency_key`; the result has
`id` and `default_manager_agent_id`. Unless you pass `default_manager_agent_id`, the call
also creates a default agent that counts against the account's agent limit),
`delete_workspace` (permanently deletes the Workspace with its files, revisions, copies and
conversations), and `get_credits`.

Runs: `send_workspace_message` (`workspace_id` and `message`) sends a message to the
Workspace's main conversation, or to the conversation named by `session_id`, and holds your
call open until the run finishes, pauses for input, or the hold ends. The default hold is
25 seconds, 50 seconds for Codex, and up to 30 minutes for Claude Code 2.1.212 or later.
A call without an MCP progressToken holds for at most 50 seconds. Pass `wait_seconds` to
set the hold yourself, up to 1800; the 50-second limit still applies without a
progressToken. The result has `agent_id` and `workspace_id`. Use that `agent_id` with
`get_run_result`, `cancel_run`, `list_runs` and `list_pending_inputs`. A result that is
still running carries `run_id` and `poll_after_seconds`, the suggested delay before you
check again. It also carries `elapsed_seconds` and, once the run records them,
`last_worklog` (the agent's own most recent note), `last_tool_step` ("running
<tool>", or "completed <tool>" between calls) and `last_activity_at`. Keep calling
`get_run_result` with `wait=true` until the run completes or needs human input.
Pass `wait=false` to `send_workspace_message` when you plan to poll instead of holding the
call open (see "Run agents in the background" below). Use `max_turn_tokens` to cap
the turn. `cancel_run` requests cancellation, and `list_runs` lists recent
runs. A new message is refused with 409 `conversation_busy` while a run in the same
conversation executes. Default task outputs go to the Workspace's persistent
`/workspace`. Use `TMPDIR` only for temporary files.

Persistence: between runs in the same Workspace, the disk under `/workspace`
persists: installed tools, cloned repos, and files. Software installed outside
`/workspace` is not kept. Ask the agent to write findings under `/workspace` when a later
run will need them. Reuse the returned `session_id` on a follow-up call that needs the
same context. A completed run alone does not prove that files are saved:
`file_source.state` `ready` with no `save_failure` means they are saved.

File references: a completed run's `files` are URLs readable with the same bearer token
as the tool call, and `read_workspace_file` reads any file of a saved revision (the
Workspace's current one, a worker's, or a changeset's). A path inside the agent's
environment such as `/workspace/reports/a.md` is not a URL; read it through one of those.

Human input: a run started through this connector pauses before each action outside the
agent's own environment (connected-account and MCP writes, outbound HTTP writes, git push,
publishing, deploys, email and others) and waits until the account owner approves that one
action. `awaiting_input` can mean an approval or a question. Show the pending
request to the human. An MCP client cannot approve an action or grant `always_allow`:
`answer_pending_input` can deny a request or answer a question the agent asks. Each
awaiting approval has an `approve_url`; give it to the human, who approves in the
Plori web app. After an answer or an approval, follow the exact
`continuation_run_id` returned by `get_run_result`. `answer_pending_input` returns the
continuation run's `run_id`, or `continuation_pending: true` while the paused run's files
are still being saved; then poll `get_run_result` on the paused run until
`continuation_run_id` is set, and poll that run.
A historical run can retain `awaiting_input` after its input has been answered.
`list_pending_inputs` returns the current queue. A row with `consent_tool`
represents an outward write. Only the human can approve it or grant standing consent
for it, in the Plori web app.

A paused run is returned inline with status `awaiting_input`. Clients that negotiate the
MCP Tasks extension receive a task handle instead and can subscribe to its status. In both
cases a call that has returned does not report later changes: poll, or keep a subscription.

Deferred work: `schedule_run` (agent_id, prompt, and delay_seconds or an RFC3339
fire_at) schedules a later run. The result has `status: "awaiting_confirmation"` and a
`confirm_url`. Show the human the prompt, the time and the `confirm_url`; the run
starts only after the human confirms it in the Plori web app.

Workers: to run several tasks at once in one Workspace, `create_workspace_worker`
(`workspace_id`, `task`, `idempotency_key`) starts a worker on its own copy of the
Workspace files and returns `worker_request_id`, `agent_id` and `task_group_id`. Pass
that `task_group_id` to later workers so they share one token limit. Poll
`get_workspace_worker` (or `list_workspace_workers`) until `save_state` is `ready`.
A completed run alone does not mean the files are saved. `get_run_result` with the
worker's `run_id` and `agent_id` reads its reply, `steer_workspace_worker` sends a
message into its running turn, `cancel_run` stops one worker and
`stop_workspace_task_group` stops a group. Workers started through this connector pause
before outward actions, like other runs. `get_workspace_costs` reports what the runs
cost.

Review: `submit_workspace_changeset` submits a worker's saved files for review against
the Workspace's current files. Poll `get_workspace_changeset` until `compared` is true
and `phase` is `review_ready`, read files with `read_workspace_file` (`revision_id` =
the changeset's `incoming_revision`), then call `accept_workspace_changeset` with
`expected_current_revision` = `comparison_current_revision` and your
`validation_evidence`, or `reject_workspace_changeset`. After one changeset is
accepted, submit the next worker again so it is compared with the new current files.
Copy deletion, file writes to a copy, conflict resolution and retention pins stay in
the REST API and the CLI.

Workflows, usage and disk reports, trash and connected accounts are not on the MCP
server; the REST API and the CLI cover them.

### Workspace CLI commands

CLI examples include the executable. When a tool takes an argument vector, start
with `plori`, then the command and its arguments.

Use exact IDs, not display names, for Workspace resources. Run `plori GROUP --help`
for the action's flags. These are CLI commands, not MCP tools. The command groups are `workspace`,
`independent-agent`, `copy`, `revision`, `workspace-files`, `worker`, `task-group`,
`changeset` and `operation`. They do not use an implicit active Workspace.

- `plori workspace create NAME --idempotency-key KEY` creates a default manager.
  Add `--manager ID` to select an existing agent. A manager that gets no messages does not run.
- `plori independent-agent create NAME --idempotency-key KEY` creates an executor.
  `plori independent-agent list` includes independent identities. Legacy
  `plori agents` keeps its compatibility inventory.
- `plori copy checkpoint WORKSPACE_ID COPY_ID --idempotency-key KEY` saves a copy.
  `plori copy clone WORKSPACE_ID --base-revision REVISION_ID --idempotency-key KEY`
  requests a proposal copy. Use `plori operation wait WORKSPACE_ID OPERATION_ID`
  to observe readiness before using its result.
- `plori task-group create WORKSPACE_ID --budget 2000000 --idempotency-key KEY`
  gives one worker a bounded token allowance. Increase it for concurrent workers.
- `plori worker spawn WORKSPACE_ID TASK --copy COPY_ID --task-group GROUP_ID
  --executor AGENT_ID --session SESSION_ID --idempotency-key KEY` selects a worker
  continuation. For new work, use `--name NAME` instead of `--executor` and omit
  `--session`. Use `plori worker status WORKSPACE_ID REQUEST_ID --wait` to inspect it.
- `plori workspace-files read WORKSPACE_ID PATH --revision REVISION_ID --json`
  reads saved text. `read-bytes` returns immutable media as base64 JSON.
  Copy writes require `--copy`, `--file` and an observed `--if-match` ETag.
  Use `--if-match 0` only to create a missing file.
- `plori changeset accept WORKSPACE_ID CHANGESET_ID --current-revision REVISION_ID
  --evidence TEXT --idempotency-key KEY` accepts reviewed changes. Use the revision
  from the comparison, not a remembered root revision. Inspect stale/conflicting
  responses and review again.
- `plori agent-stop AGENT_ID` stops execution. `plori agent-retire AGENT_ID --yes`
  prevents future assignments. `plori workspace delete WORKSPACE_ID --yes`
  requests destructive deletion. Use `--yes` only for an authorized action.

A task group's budget is a token limit its workers share, not a cost; `get_workspace_costs`
reports cost. Omit the optional budget fields to keep the configured defaults; an explicit
advisor budget of 0 disables advisor reviews. The single-worker example in
https://plori.ai/docs/cli shows the sizes.

## Run agents in the background

A run can outlast the call that started it. Pick the option below that fits your
client, instead of holding a call open for a job that takes minutes.

- **Claude Code**: the server can hold a call up to 30 minutes for Claude Code 2.1.212 or
  later, but Claude Code moves a call that runs past about two minutes to the background
  and can drop its result, so hold each `get_run_result` call to about 100 seconds
  (`wait_seconds: 100`). Keep at most one held call per run in flight. Between
  calls, poll with `wait=false` on a short cadence. Read `tool_progress`
  (`completed_count`, `last_completed_at`) and `elapsed_seconds` on the returned
  result to judge progress. To watch every run on the account instead, use `Monitor`
  on `wss://api.plori.ai/v1/events` with the WebSocket protocols
  `["plori", "plori.bearer.<API key>"]`. Running `plori watch` in a background shell
  works too.
- **Codex**: set `tool_timeout_sec` on the plori server entry in `config.toml` to at
  least as long as the work you expect. Another option: run `plori watch` in a
  background shell, then check `plori inbox` for what finished.
- **Any other client**: pass `wait=false` to `send_workspace_message`. Call
  `get_run_result` again after `poll_after_seconds`. Repeat until the status is
  terminal or `awaiting_input`.

## CLI commands

The CLI covers the same operations and more, including those that are not MCP tools. An
agent is addressable by name or id, and every command accepts `--json`.

- `plori attach <name|session-id>`: open a live session in the terminal (history, a
  prompt, streaming output, and approvals answered in place). It is interactive and
  expects a human at the keyboard: as a calling agent, prefer the one-shot commands
  below, and use `--read-only` if you only need to tail a session. It writes plain
  text, never JSON, and redirecting stdin or stdout already selects read-only.
- `plori create <name>`: get or create an agent by name (reusing a name returns the
  existing agent). `plori agents`, `plori agent <name>`, `plori set-model <name> <model>`,
  `plori delete <name> --yes`.
- `plori run <name> "message"`: send a message and, by default, wait for the reply and
  print it. Add `--follow` to stream the turn live, `--jsonl` for a machine-readable
  event stream, or `--no-wait` to get a run id back immediately. Pass `-` as the
  message to read it from stdin.
- `plori result <name> <run-id>` (add `--wait`, bounded by `--wait-seconds`, to
  block) and `plori runs <name>` read run status and history.
- `plori watch [--agent <name|id>]...`: stream run endings and human-input requests as
  JSON lines until stopped. Run it in a background shell alongside a `--no-wait` run.
- `plori inbox [--ack <run-id>]`: one-shot summary of what ended since your last
  acknowledgement, plus everything waiting on you.
- `plori inputs <name>` lists runs paused on a human request; `plori answer <run-id>
  <tool-call-id> --approve|--deny|--value <v>` replies. Add `--always-allow` to an
  `--approve` (only on the human's explicit instruction) to also grant the standing
  write consent.
- `plori schedule <name> "prompt" --in <seconds>` (or `--at <rfc3339>`) defers a run;
  `plori schedules <name>` and `plori unschedule <name> <id>` manage them.
- `plori workflows list [--agent <name|id|none>]`,
  `plori workflows create <name> [--trigger cron --cron <expr>]`,
  `plori workflows run <name|id>` (run it now), `plori workflows execution <name|id> <exec-id>`.
- `plori credits`, `plori usage`, `plori disk` read account state.

`plori run`, `plori result --wait` (bounded by `--wait-seconds`), and `plori watch`
report the run's outcome as an exit code:

| code | meaning |
| ---- | ------- |
| 0 | succeeded |
| 1 | API or runtime failure |
| 2 | usage error |
| 3 | missing, rejected, or expired credentials |
| 4 | could not reach the control plane |
| 10 | the run is awaiting human input |
| 20 | the run ended in error |
| 30 | the run was cancelled |
| 40 | a wait ran out with the run still going |

## Costs and limits

Running an agent spends credits; check `get_credits` before invoking. The account's
plan sets its included monthly credits and its disk. It also sets the agent count,
active workflows, workflow concurrency, and the length of one run.

Registered accounts have no limit on concurrent agent runs.
Anonymous trials allow at most 2 concurrent agent runs across their agents.
A third run makes `send_workspace_message` return 429 with advice to register free to remove the limit.

The plan does not set the model: the
Plori Router picks it, the same way on every plan. Every call is scoped to the account
that owns the credential; there is no cross-account access.

### What to expect

Cost and duration scale with what a turn does, not with its length alone. Three runs
measured on 2026-09-13 on one agent:

- A read-only account inventory (45 tool calls): about $0.14, 5 minutes.
- A planning turn that read 13 web pages and one ads API (67 calls): about $1.39,
  9 minutes.
- A build turn (110 calls): about $0.58, 30 minutes.

Plori bills model usage, but automatically refunds charges when a platform fault stops
the run, subject to a per-account rolling 24-hour limit. `max_turn_tokens` and
`max_turn_seconds` cap a turn's tokens and wall time.

## More

- Integration entry point: https://plori.ai/agents.md
- MCP connect guide: https://plori.ai/mcp
- CLI on npm: https://www.npmjs.com/package/@plori/cli
- Authentication detail: https://plori.ai/auth.md
- Site map for agents: https://plori.ai/llms.txt
