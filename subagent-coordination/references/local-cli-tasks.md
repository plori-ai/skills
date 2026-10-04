# Local CLI tasks

Read this when the coordinator assigns a unit to the other installed coding harness. These
commands are templates, not a reason to fill unused slots. Apply the skill's limits (3 native,
2 CLI, 5 total) before launching or resuming. CLI workers must not delegate.

## Prepare

1. Check `command -v codex` or `command -v claude`, its version, and its current `--help`.
   Flags and accessible models differ between the native tool and the local CLI, and a CLI
   accepting a model string does not prove the account can use it.
2. Write the complete worker brief to a file. Set `task_worktree` to the directory the worker
   edits: the coordinator's shared checkout by default, or the unit's own worktree under the
   skill's exceptions. Set `task_worktree`, `task_brief`, and `task_output` to absolute paths
   and create the output directory. Set `task_model` explicitly from the skill's tier table.
3. Record the task in the coordination log and reserve a slot. Launch with the working
   directory set to `task_worktree`, through a mechanism the coordinator can track (the
   harness's managed background job, or the detached launch below with a PID file and a
   monitor). Do not leave an untracked `nohup` or bare `&` process.

The examples reuse existing local authentication. Pass the brief on stdin so its content is
not evaluated as shell code. Use a new output directory for every invocation, follow-ups
included, so earlier evidence is kept.

## Claude Code coordinator -> local Codex worker

For an editing task:

```sh
codex -a never exec -C "$task_worktree" -m "$task_model" \
  --sandbox workspace-write --json \
  -o "$task_output/report.md" - \
  < "$task_brief" > "$task_output/events.jsonl" 2> "$task_output/stderr.log"
```

For a read-only investigation use `--sandbox read-only`. `-a never` disables approval prompts;
it does not grant access that is otherwise denied, so the worker returns a denied step to the
coordinator as a blocker. `-C` is required: without it Codex refuses to run outside a trusted
directory. Keep session persistence on and save the thread ID from the event stream. See
[Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).

**When the Codex sandbox cannot start.** In some containers and VMs every command the worker
runs fails with `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`; the worker then
reports "blocked" after about a minute with no changes. In that environment, and only when
the coordinator's own session already runs without permission prompts (for example a
bypass-permissions session), use `--sandbox danger-full-access` with `-a never`: the worker
then has the same access the session's native subagents have. Otherwise keep the unit on a
native worker. Do not use it to get past a restriction the coordinator itself is under.

**Detached launch.** If the harness stops background shell commands before a worker can
finish, launch detached with `setsid`, and write a PID file and an exit file:

```sh
mkdir -p "$task_output"
setsid bash -c "cd '$task_worktree' && codex -a never exec -C '$task_worktree' \
  -m '$task_model' --sandbox workspace-write --json \
  -o '$task_output/report.md' - < '$task_brief' \
  > '$task_output/events.jsonl' 2> '$task_output/stderr.log'; \
  echo \"exit \$?\" > '$task_output/exit'" > /dev/null 2>&1 < /dev/null &
echo $! > "$task_output/pid"
```

Watch it with a monitor that waits on the PID and is re-armed while the PID is alive:
`P=$(cat "$task_output/pid"); while kill -0 $P 2>/dev/null; do sleep 30; done; echo "codex
exited: $(cat "$task_output/exit")"`. A report under 1 KB after a one-minute run usually means
the worker was blocked, not done; read `report.md` before relaunching.

To watch several workers in one monitor, name them literally and mark each reported exit with
a file. This form works in both bash and zsh:

```sh
while true; do alive=0
  for n in unit-a unit-b unit-c; do
    [ -f "$D/$n/.reported" ] && continue
    if kill -0 "$(cat "$D/$n/pid")" 2>/dev/null; then alive=1
    else echo "codex $n exited: $(cat "$D/$n/exit")"; touch "$D/$n/.reported"; fi
  done
  [ $alive = 0 ] && break; sleep 20
done
```

Working with Codex workers:

- A running `codex exec` worker cannot receive messages; the native messaging tool reaches
  native workers only. Put every decision and constraint in the brief before launch. To
  correct a worker, wait for it to exit and launch a new `codex exec` in the same directory
  with a short delta brief that names the worker's own changes (its files in the shared
  checkout, or its commit), the coordinator's decisions, and a new output directory.
- Keep one shared brief tail (hard rules, report format, trailers) in a file and append it to
  every unit's brief, so the rules are identical across units.
- Codex reports are compact and cite `file:line`. Still read the diff: a report can be
  accurate about what it lists and silent about a behavior change only the diff shows.

## Codex coordinator -> local Claude Code worker

Run from `task_worktree`. For an editing task:

```sh
claude -p --model "$task_model" \
  --permission-mode acceptEdits --permission-prompts none \
  --tools 'Read,Glob,Grep,Edit,Write,Bash' \
  --output-format stream-json --verbose \
  < "$task_brief" > "$task_output/events.jsonl" 2> "$task_output/stderr.log"
```

`acceptEdits` permits file edits but not arbitrary shell commands, and
`--permission-prompts none` denies any action that would prompt. Allow the task's test and
build commands with scoped `--allowedTools` rules before launch; the worker reports any denial
that remains. For file-only research use `--permission-mode dontAsk` with
`--tools 'Read,Glob,Grep'`. The tool list leaves out the native delegation tools, and the brief
also forbids launching coding agents through Bash.

Keep the session ID and final result from the stream, and do not pass
`--no-session-persistence` when follow-ups may be needed. See
[Claude Code headless mode](https://code.claude.com/docs/en/headless).

## Supervise, resume, and integrate

- Poll the process and its output while doing other coordination work. A quiet log does not
  mean the task exited. Capture the exit status and read error and final-result events; exit
  code 0 alone does not prove the deliverable.
- Apply the skill's 15-minute inactivity check: record when output last changed and the next
  inspection time, and wake even if the CLI prints nothing. At the deadline inspect the
  process, logs, child processes, and permission waits, and intervene if needed. A healthy
  quiet operation gets another timed check, not termination.
- For a follow-up, wait for the exit and reserve a slot again. Codex: launch a new
  `codex exec` in the same directory with a delta brief and a new output directory. Claude
  Code: target the saved session with `claude -p --resume SESSION_ID`, and pass the model,
  permissions, output capture, and stdin brief again. Never use `--last` or `--continue` to
  pick among concurrent tasks.
- On failure, keep partial output and the worker's files (or its worktree). Inspect before
  retrying, and confirm the old process and its background work have stopped before starting
  a replacement.
- On success, check the actual diff, untracked files, test evidence, and stated omissions.
  Preserve the deliverable before removing a worker's own worktree. Workers do not merge,
  deploy, publish, or write to shared systems. Do not use permission-bypass flags to get around
  the coordinator's own restrictions.
