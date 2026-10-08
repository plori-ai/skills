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

### Steerable launch (preferred)

`codex exec` reads its brief once, takes no messages while it runs, and starts a full Codex
process per worker. Launch Codex workers through this skill's `scripts/codex-steer.py`
instead. It runs every worker as a thread in one shared `codex app-server`, owned by one small
daemon per pool, and lets the coordinator message a running worker the way it messages a
native subagent. Measured with codex-cli 0.161: ten concurrent workers used about 200 MB in
total (daemon about 23 MB, app-server about 180 MB) instead of about 260 MB per worker, and
the idle daemon uses no CPU. It needs Python 3.8+ (standard library only) and a Codex CLI whose
`app-server` has `turn/steer`. If either is missing, use the `codex exec` launch below.

```sh
steer="<this skill's directory>/scripts/codex-steer.py"
python3 "$steer" run --cwd "$task_worktree" --out "$task_output" --model "$task_model" \
  --sandbox workspace-write < "$task_brief"
```

`run` returns as soon as the worker's first turn has started and prints the task state as one
JSON line. The first `run` starts the pool's daemon; the daemon starts the app-server, and both
exit after `--idle-exit` seconds (default 300) with no live task. No per-worker process is left
behind, so there is no PID to track: the task is finished when `$task_output/exit` exists.
The daemon is detached from the shell that ran `run`, so a harness limit on background shell
commands does not end the worker. The daemon's socket lives under
`${XDG_RUNTIME_DIR:-/tmp}`, and a reboot ends every task: keep `$task_output` on a path that
survives a reboot, and continue an ended task with `--resume`.

Options: `--sandbox read-only|workspace-write|danger-full-access` (default `workspace-write`),
`--approval` (default `never`; approval requests that still arrive are declined, and the
worker reports the blocker), `--effort low|medium|high`, `--linger SECONDS` (keep the task
open that long after its last turn to accept a follow-up), `--resume THREAD_ID`, `-c
key=value` (Codex config for this worker's thread only), and `--wait` (block until the task
ends and exit with its code). `--codex PATH` and `--daemon-config key=value` apply to the
shared app-server and take effect only when that `run` starts the daemon. `--pool NAME` (or
`CODEX_STEER_POOL`) selects a separate daemon, for example one per `CODEX_HOME`. The sandbox
rules below apply unchanged.

Files in `$task_output`: `state.json` (thread ID, active turn, `status` = `running`, `idle` or
`exited`, `lastActivityAt`, `lastError`), `report.md` (final message of the latest turn) and
`turns/N.md` (each turn's final message), `events.jsonl` (this thread's app-server
notifications without streaming deltas), `steer.log`, `thread_id`, and `exit` (`exit N` once
the task has ended: 0 last turn completed, 1 failed, 2 interrupted or stopped, 3 startup or
protocol error, including an app-server crash). The daemon's own log is under
`${XDG_RUNTIME_DIR:-/tmp}/codex-steer-$UID/`. Exit 0 means the last turn completed, not that
the work succeeded: a worker whose every command failed (for example the sandbox error under
"When the Codex sandbox cannot start") reports the error text as its answer and still exits
0. Read `report.md` before accepting.

Wait for workers with one process for all of them, run as the harness's tracked background
job or as a monitor command (one event per ended task; re-arm it on expiry while tasks are
live); it prints one JSON line per task as each ends. For the 15-minute silence check, read
`lastActivityAt` in each task's `state.json`:

```sh
python3 "$steer" wait "$out_a" "$out_b" "$out_c"          # until all end; exit = worst code
python3 "$steer" wait --any --timeout 900 "$out_a" "$out_b" # first to end, or 124 on timeout
```

Message a running worker:

```sh
python3 "$steer" send "$task_output" "Interface decided: use FooConfig, not a dict."
python3 "$steer" send "$task_output" - < "$delta_file"          # longer message
python3 "$steer" send "$task_output" --interrupt "Stop: X is wrong. Do Y instead."
python3 "$steer" interrupt "$task_output"   # stop the current turn, keep the task
python3 "$steer" stop "$task_output"        # stop the turn and end the task (exit 2)
python3 "$steer" status "$task_output"      # or with no directory: every task in the pool
```

`send` prints one JSON line with the delivery result:

- `steered`: added to the running turn. The model sees it at its next step, after the current
  model response or tool call returns, without losing work in progress. A long test command
  delays it until the command ends; use `--interrupt` when that is too late.
- `queued`: the turn could not take input (it was ending, or is a review or compact turn), so
  the message starts the next turn in the same thread as soon as this one finishes.
- `started`: the task was idle (lingering) and the message started a new turn.
- `undelivered`: the task has ended or its pool is not running. Use a follow-up launch.

`--interrupt` stops the current turn first, then delivers the message as the next turn in the
same thread, so the worker keeps its context and its changes. A task ends once its last turn
ends and no message is waiting (after `--linger`, if set).

To follow up after a task has ended, resume its thread in a new output directory instead of
starting a fresh `codex exec`. The worker keeps its full context, so the brief only needs the
delta:

```sh
python3 "$steer" run --cwd "$task_worktree" --out "$task_output_2" --model "$task_model" \
  --resume "$(cat "$task_output/thread_id")" < "$delta_brief"
```

All workers in a pool share one app-server: if it crashes, every live task in the pool ends
with exit 3 and `lastError` says so; the next `run` starts a new app-server, and each task can
continue with `--resume`. `python3 "$steer" daemon stop` ends every task in the pool.

### `codex exec` launch (fallback)

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
native worker. Do not use it to get past a restriction the coordinator itself is under. The
same applies to the steerable launch: under `codex app-server`, `workspace-write` fails with
the same error (verified with codex-cli 0.159.3), so pass `--sandbox danger-full-access` to
`codex-steer.py run` in that environment.

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

- A worker launched with `codex-steer.py` takes messages through `send`; the native
  messaging tool reaches native workers only. Use `send` for decisions made after launch, a
  correction, a new constraint from another unit, or a request for a progress report. Each
  message must make sense on its own; log each one in the coordination log. Use
  `--interrupt` when the worker is on a wrong path, not for routine additions.
- A running `codex exec` worker cannot receive messages. Put every decision and constraint
  in the brief before launch. To correct it, wait for it to exit and launch a new
  `codex exec` in the same directory with a short delta brief that names the worker's own
  changes (its files in the shared checkout, or its commit), the coordinator's decisions, and
  a new output directory.
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
- For a follow-up, wait for the exit and reserve a slot again. Codex: with `codex-steer.py`,
  `run --resume` the saved thread ID with a delta brief and a new output directory; with
  `codex exec`, launch a new `codex exec` in the same directory with a delta brief and a new
  output directory. A message to a running steerable worker is not a follow-up launch and
  needs no new slot. Claude
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
