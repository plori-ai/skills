# plori Agent Skills

[![Install with skills.sh](https://skills.sh/b/plori-ai/skills)](https://skills.sh/plori-ai/skills)

Instructions for coding agents to use [plori](https://plori.ai): a cloud AI agent
with its own persistent environment.

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

## Skills

| Skill | What it teaches |
| --- | --- |
| [`plori`](./plori/SKILL.md) | Connect to plori over MCP, the `@plori/cli` command, or REST, authenticate (OAuth 2.1 or API key), create agents, invoke them and read replies, answer human-in-the-loop requests, schedule deferred runs, build and run workflows |

## Notes

- These skills mirror the canonical copies served at
  `https://plori.ai/.well-known/agent-skills/` (Agent Skills Discovery RFC); both are
  generated from the same source and updated together on every plori release.
- plori also runs a remote MCP server at `https://api.plori.ai/mcp` for clients with
  native MCP support, and ships a CLI ([`@plori/cli`](https://www.npmjs.com/package/@plori/cli),
  `npm i -g @plori/cli`) for terminal agents; the skill covers all three paths.
- Questions or issues: [dev@plori.ai](mailto:dev@plori.ai) or
  [github.com/plori-ai/plori](https://github.com/plori-ai/plori).

## License

MIT
