# plori Agent Skills

[![Install with skills.sh](https://skills.sh/b/plori-ai/skills)](https://skills.sh/plori-ai/skills)

Instructions for coding agents to use [plori](https://plori.ai): a cloud AI agent
with its own persistent environment. The repository also holds general skills that
the plori team wrote for its own work in Claude Code and Codex.

## Connect from Claude Code

Paste this into an interactive Claude Code conversation:

> Read https://plori.ai/.well-known/agent-skills/plori/SKILL.md and install/connect Plori over MCP.

Claude reads the instructions and configures MCP if needed. When a new server has
not loaded, it asks you to type `/reload-plugins` in the same conversation. With
pairing, open the short address Claude shows, enter the code, verify your email,
and approve the connection. You can approve from a phone while Claude Code runs on
a remote machine.

No installed skill or plugin is required for this flow. Other clients use their
own setup steps in the [connection guide](https://plori.ai/mcp).

## Install the skill for reuse

To keep these instructions available across conversations, install the skill:

```sh
npx skills add plori-ai/skills
```

This command installs every skill in the repository. To install one skill, name it:

```sh
npx skills add plori-ai/skills --skill subagent-coordination
```

## Skills

| Skill | What it teaches |
| --- | --- |
| [`plori`](./plori/SKILL.md) | Connect to plori over MCP, the `@plori/cli` command, or REST, authenticate (OAuth 2.1 or API key), create agents, invoke them and read replies, answer human-in-the-loop requests, schedule deferred runs, build and run workflows |
| [`subagent-coordination`](./subagent-coordination/SKILL.md) | Run a multi-part coding task as a coordinator: plan, split the work into units that own separate files, brief up to five workers (native subagents plus tasks in the other local coding CLI), review each result before you accept it, and ship one PR |
| [`root-cause-debugging`](./root-cause-debugging/SKILL.md) | Find the root cause of an incident or a recurring bug: build an evidence timeline, answer three causal questions, check current upstream guidance, and design a fix for the mechanism, not the symptom |
| [`record-live-demo`](./record-live-demo/SKILL.md) | Record a real terminal, browser, or desktop product demo, then verify it and make an H.264 MP4 for delivery, with trim and speed helpers |

## Notes

- The `plori` skill mirrors the canonical copy served at
  `https://plori.ai/.well-known/agent-skills/` (Agent Skills Discovery RFC); both are
  generated from the same source and updated together on every plori release.
- `subagent-coordination`, `root-cause-debugging`, and `record-live-demo` are
  general skills. They do not need a plori account.
- plori also runs a remote MCP server at `https://api.plori.ai/mcp` for clients with
  native MCP support, and ships a CLI ([`@plori/cli`](https://www.npmjs.com/package/@plori/cli),
  `npm i -g @plori/cli`) for terminal agents; the skill covers all three paths.
- Questions or issues: [dev@plori.ai](mailto:dev@plori.ai) or
  [github.com/plori-ai/plori](https://github.com/plori-ai/plori).

## License

MIT
