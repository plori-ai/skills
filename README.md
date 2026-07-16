# plori Agent Skills

[![Install with skills.sh](https://skills.sh/b/plori-ai/skills)](https://skills.sh/plori-ai/skills)

Skills that teach any coding agent (Claude Code, Codex, Cursor, Copilot, Gemini CLI,
and 40+ other clients) how to use [plori](https://plori.ai): cloud computers for AI
agents, with persistent disks, real tools, and memory that survives between sessions.

## Install

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
