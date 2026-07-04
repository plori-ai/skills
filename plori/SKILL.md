---
name: plori
description: Create and drive plori agents (each an AI agent on its own cloud computer) from any MCP client or over REST. Covers authentication (OAuth 2.1 or API key), creating agents, invoking them and reading replies, answering human-in-the-loop requests, and scheduling deferred runs.
---

# Using plori from an agent

plori (https://plori.ai) hosts AI agents. Each agent runs on its own cloud computer with a
persistent disk, a shell, developer tools, and memory. You can create agents, send them
work, and read their replies programmatically.

## Connect

MCP (recommended): Streamable HTTP at `https://api.plori.ai/mcp`.

- OAuth 2.1: compliant MCP clients connect with no hand-copied key. An unauthenticated
  request returns 401 with the discovery chain (RFC 9728 Protected Resource Metadata at
  https://api.plori.ai/.well-known/oauth-protected-resource, then dynamic client
  registration and authorization code + PKCE). The account owner signs in once with an
  email one-time code.
- API key: the account owner provisions a key at https://plori.ai and you send
  `Authorization: Bearer plori_sk_...`.

REST: the same operations at `https://api.plori.ai/v1` with the same bearer token.
Full authentication instructions: https://plori.ai/auth.md

## Tools

Account and agents: `list_brains`, `list_agents`, `get_agent`, `create_agent`
(name, optional model), `set_agent_model`, `delete_agent`, `get_credits`,
`get_usage`, `get_disk`.

Runs: `invoke_agent` sends a message and by default blocks until the turn finishes,
returning the assistant's reply. Pass `wait=false` to get a `run_id` immediately and
poll `get_run_result`. `list_runs` lists recent runs.

Human in the loop: a run can pause on an approval or input request (status
`awaiting_input`). Read the queue with `list_pending_inputs` and reply with
`answer_pending_input` (run_id + tool_call_id, then approved=true/false for approvals
or value for input requests).

Deferred work: `schedule_run` (agent_id, prompt, and delay_seconds or an RFC3339
fire_at) invokes the agent later as an ordinary run.

## Costs and limits

Running an agent spends credits; check `get_credits` before invoking. Agent count and
model tier follow the account's plan. Every call is scoped to the account that owns the
credential; there is no cross-account access.

## More

- Integration front door: https://plori.ai/agents.md
- MCP connect guide: https://plori.ai/mcp
- Authentication detail: https://plori.ai/auth.md
- Site map for agents: https://plori.ai/llms.txt
