---
name: subagent-coordination
description: Gather context, plan, and coordinate multi-step coding work in Claude Code or Codex with explicit model tiers. Splits the work into file-disjoint units for up to three native subagents and two tasks in the other local coding CLI running at the same time, reviews every deliverable before accepting it, integrates the units locally without per-unit CI runs or PRs, and ships the reviewed whole as one PR. Use when work divides into independent deliverables, such as a multi-part feature, a batch of CI failures, or a large refactor. Do very simple tasks directly instead.
---

# Subagent coordination

The coordinator (the main session) owns the goal, the sequencing, the integration, and every
write to a shared system. It delegates bounded research, implementation, tests, and drafting,
then plans, reviews, and integrates. Workers hand back artifacts and evidence; the coordinator
decides whether to accept them. The coordinator takes over a unit itself when the unit is too
entangled to brief or a worker stays stuck after one correction.

## 0. Gather context, then plan, then delegate

- **Do very simple tasks directly.** An obvious small edit, a known command, or a narrow
  lookup needs no workers, coordination log, or formal plan.
- **Gather context before orchestrating.** Confirm the user's goal and constraints, read the
  repository's instruction files, inspect the relevant code, docs and worktree state, and
  identify dependencies and unknowns. Gather enough to plan soundly; this pass does not need
  to solve every implementation detail.
- **Plan before assigning workers.** State the outcome and acceptance criteria, choose the
  approach and sequence, then split the work into bounded deliverables with owners and
  dependencies. Mark which units can run together and which need earlier results.
- **Research first when an unknown blocks the plan.** Dispatch one bounded research unit,
  review its evidence, and revise the plan before dispatching implementation that depends on it.

## 1. Concurrency

- **Limits: at most 3 native subagents, at most 2 tasks in the other local coding harness, at
  most 5 ongoing worker tasks in total.** The coordinator is not counted. A Claude Code
  coordinator runs the two non-native tasks as local `codex exec` processes; a Codex
  coordinator runs them as local `claude -p` processes (§3). These are ceilings, not targets.
  Unused CLI capacity does not allow a fourth native worker, and unused native capacity does
  not allow a third CLI task. If the harness counts the coordinator in its own agent cap, use
  the smaller number.
- **Count ongoing work, not tool calls.** A task waiting on a tool, test, or permission still
  holds its slot. An idle native session with no running work does not, but resuming it needs
  a free slot. A CLI task holds its slot until its process and any background work it started
  have exited.
- **Fill free slots, then one in, one out.** Dispatch independent units together within the
  limits. Free a slot only after confirming completion or termination; a progress message or a
  timeout is not completion.
- **Keep one coordination log for every kind of task.** Per task: ID, kind (native or CLI),
  harness, explicit model, owned paths, agent/process/session handle, output paths,
  state, `last_activity_at`, and `next_check_at`. Keep queued work in the same log and check
  the counts before every launch or resume.
- **Split for concurrency by file ownership.** Aim for as many units as can run at once
  without touching each other's files: one deliverable or failure class per unit, split along
  package, module, or directory lines, each unit owning an explicit list of files and
  directories with its tests. Two workers never edit the same file; combine or sequence units
  whose edits overlap. Files that several units would change (dependency manifests and
  lockfiles, generated code, migration numbering, golden files, shared registries) belong to
  the coordinator or to one designated unit that changes them after the others. When the work
  does not divide into disjoint file sets, run fewer units or do it directly.
- **Write shared contracts first.** When two units need the same new types, wire fields,
  interface, or test fake, the coordinator writes that part before dispatch, so it is already
  in the tree (or in a small base commit for a unit on its own branch). Give each brief the
  exact names and signatures and say they are fixed. A worker that needs the other side before
  it exists adds a clearly marked stub file that the coordinator deletes at integration.
- **No recursive delegation.** Workers of every kind must not spawn subagents, invoke another
  coding agent, or create agent teams. Only the coordinator dispatches.

### One checkout, one PR

Editing workers work in the coordinator's checkout, on the one branch the change ships from,
and the combined change goes out as one PR. File ownership isolates the units, so integrating
a unit means reviewing its files, not merging branches.

- **Shared checkout (default).** Native and local CLI workers edit the coordinator's working
  tree directly, each in its own file set. Before dispatch, record the base commit
  (`git rev-parse HEAD`) and the ownership map in the log. Workers make no git writes (§4). On
  each report the coordinator reviews `git diff -- <owned paths>` and new files under those
  paths, checks `git status` for changes outside the map, and on Accept may commit that unit's
  paths as a local checkpoint. Nothing is pushed. Run a milestone check (§8) only when no unit
  is still editing the packages it covers, or it can fail on another unit's unfinished edits.
- **Own worktree on a local branch (exception).** Give a unit its own worktree only when it
  cannot share the tree: it must build or test in isolation while other units are mid-edit,
  it runs a generator that rewrites files it does not own, or its files cannot be separated
  from another unit's but the two can run one after the other. The worker commits on a local
  `unit/<name>` branch; the coordinator merges it locally (`git merge --no-ff`, or a
  cherry-pick), removes the worktree, and deletes the branch. The branch is never pushed and
  never gets its own PR.
- **No per-unit CI, full builds, or PRs.** Units hand back source (§8). Checks run on the
  combined tree at milestone boundaries and in the final verification phase. The coordinator
  then reviews the whole diff against the base once and opens one PR. Split into several PRs
  only when the plan ships parts on different branches or at different times.

## 2. Model choice

The coordinator keeps its session model. Choose each worker's model by the judgement the unit
needs. The table pairs tiers across harnesses for routing; it does not claim the models are
equal.

| Task | Claude Code | Codex |
| --- | --- | --- |
| Design, nontrivial implementation, debugging, root-cause analysis, substantive review | `opus` | the newest generation's flagship |
| Bounded implementation with a clear recipe, tests to a spec, code search, data collection, report drafts | `sonnet` | the newest generation's mid tier |
| Trivial mechanical edits, renames, list extraction, formatting named files | `haiku` | the newest generation's small tier |

- **Use the newest model in each tier; never pin a version.** On Claude Code use the aliases
  `opus`, `sonnet`, and `haiku` (native `Agent` tool and `claude -p --model`); they resolve to
  the newest model of each family, so never write a dated model ID. Codex has no floating
  alias: at launch, run `codex debug models`, take the newest generation among the listed
  slugs, and map its flagship, mid, and small models to the three tiers. Record the resolved
  slug in the log.
- **Set the model explicitly** on every native spawn and CLI launch; do not inherit the
  coordinator's model. Move a unit up a tier when the evidence shows it needs more judgement.
- **Check the actual surface.** A model offered by native tools may not be available to the
  local CLI account, and a CLI accepting a model string does not prove access. If a tier is
  unavailable, say so, pick an available model explicitly, and record the substitution. Do not
  invent IDs.
- **Codex native tools:** when `spawn_agent` exposes `model`, pass it explicitly with
  `fork_turns: "none"` (or a supported bounded history); full-history forks can inherit the
  parent model and reject overrides. Give a self-contained brief either way.
- **Claude Code native tools:** pass `model: "opus"`, `"sonnet"`, or `"haiku"` to `Agent`.
  Leave isolation unset for a unit in the shared checkout; request worktree isolation only for
  a §1 exception.

## 3. Local tasks in the other harness

Use the two non-native slots for an independent implementation, investigation, or review when
it helps the work: Claude Code drives local `codex exec`, and Codex drives local `claude -p`.
Read [references/local-cli-tasks.md](references/local-cli-tasks.md) before launching. Check the
executable, its flags, model access, and existing authentication without printing
credentials. If it is unavailable, keep the unit queued or use a free native slot; do not
install software, change credentials, or exceed the native limit to compensate.

Local CLI tasks edit the shared checkout like native workers, with absolute brief and output
paths, and get a worktree only under §1's exceptions. A read-only worker whose evidence depends
on files another unit is editing waits for that unit or reads the base commit
(`git show <base>:<path>`). CLI tasks have the same brief, permission, verification, and
cleanup obligations as native workers.

## 4. The brief

Every brief has these seven parts. Do not rely on inherited conversation history. Tell the
recipient it is a bounded worker even if the repository's instructions describe coordinator
mode, and that it must not delegate or launch another coding agent.

1. **Established facts:** what is already known and verified (commits, numbers, prior
   findings, paths), plus the overall goal and this unit's role in the plan, so the worker
   does not re-derive them.
2. **The task:** the outcome, the acceptance criteria, and the expected output. Use numbered
   steps only where order matters (a migration, an auth flow, a destructive command); for
   judgement work state the goal and constraints and let the worker plan.
3. **Phase and verification role** under §8: implement (hand back code and test sources, with
   checks reported as deferred, not run), run a milestone's minimum check, or verify the
   completed project. Verification briefs name exact commands and the evidence wanted. When
   the unit changes a contract other code encodes (CLI flags, exit codes or output fields;
   REST, RPC or event shapes; tool schemas; golden files), grep the repository for the old
   value before writing the brief, and either put every suite that pins it in scope or assign
   those suites to a sibling unit. A worker limited to one module cannot see them.
4. **Hard rules:** what it must not touch or do, written out in full, because each worker
   starts without the coordinator's context. Typical set: no deployments, no merges to
   protected branches, no writes to trackers, shared staging, or other shared systems, no
   tree-wide formatters, no destructive git operations, no credentials in output, no
   delegation. Run long commands in the foreground: a worker that ends its turn waiting on a
   background job is never resumed.
5. **Problems and blockers:** stop speculative changes and report the observed problem
   promptly. Before concluding or proposing a fix, search upstream issues, documentation, and
   discussions for prior solutions and check they fit our versions and constraints (§6).
   Return source links, tradeoffs, and a recommendation. A design gap or wrong premise goes
   back to the coordinator before the agreed approach or scope changes.
6. **Report shape:** fields, numbers, `file:line` evidence, pass/fail per check, known limits,
   and every deviation from the brief with its reason. Ask for evidence, not adjectives.
7. **Handoff and cleanup:** report changed and new files (shared checkout) or the branch and
   commit (own worktree), test output, and processes it started. Stop its own
   background work. An own worktree stays until the coordinator has merged its branch; then
   the coordinator removes it, because stale worktrees keep their build output and caches on
   disk. Never discard uncommitted work to free a slot.

Also put the commit attribution trailers in the brief, written out, or the worker invents its
own.

A brief for a unit in the shared checkout adds its owned paths and these rules:

- Edit and create files only under the owned paths. Report a change needed elsewhere with its
  exact content instead of making it.
- No git writes: no `add`, `commit`, `stash`, `checkout`, `restore`, `reset`, `switch`,
  `merge`, `rebase`, or `clean`. Read with `git --no-optional-locks status` and
  `git diff -- <owned paths>`. Other modified files belong to other units; leave them alone.
  `git stash` in a shared checkout takes every unit's edits.
- No tool that writes outside the owned paths: no tree-wide formatter, dependency tidy,
  code generator beyond the owned packages, or package install that rewrites a lockfile.
  Format owned files only.
- A narrow diagnostic may see another unit's unfinished edits. Report a failure outside the
  owned paths; do not fix it.

Add these when they apply to your environment:

- **Secrets.** Never write a decrypted secrets file or an environment dump to disk. Read one
  key per command into a variable, and print lengths, never values. If the shell has wrappers
  or aliases that rewrite command output (token-saving proxies, pagers, `grep`/`cat`
  replacements), call the real binary (`command grep`, `command git diff`) near secrets and
  wherever exact output matters: a wrapper can print file contents instead of a count,
  truncate a long document, or turn `git diff` output into something that is not a patch.
- **No build outputs in commits.** Building inside a module directory can drop a binary
  there. Build to a scratch path and check `git status` for untracked binaries before
  committing.
- **Callers of a changed interface.** A unit that changes a script's arguments, a CLI, a wire
  type, or a shared fake greps the whole repository for callers and updates or lists them.
- **Fresh lint caches.** A shared linter cache can report findings for worktrees that no
  longer exist; run lint with its cache directories set to a fresh location.
- **Live resources.** A worker that must create or change something in a real account gets an
  explicit block: who approved it, exactly which resources it may create (count, shape,
  labels, nothing that production automation discovers), what it must not touch, a time
  limit, and cleanup it verifies through the provider's API before reporting. The coordinator
  checks the resource from outside while the worker runs.

## 5. The loop

1. **Gather context and plan before the first dispatch** (§0). Before each later wave, review
   new evidence against the goal, update the plan, then choose the next units.
2. **Write the briefs** (§4), choose explicit models, and record the queue and file ownership.
3. **Dispatch** within the limits (§1). Start each worker's inactivity timer and keep the
   supervision loop (§6) running while any delegated work is ongoing; do not wait only for
   completion notifications.
4. **Review each report and give a verdict before integrating** (below). A completion message
   or passing tests is not acceptance. Review source and contracts before integrating; checks
   follow the §8 schedule, not a gate per worker. Build dependent work only on reviewed work.
5. **Log** to an append-only coordination log with timestamps from the clock (`date -u`),
   never from memory: worker completion, the verdict and its reasons, integration, and cleanup,
   as separate entries with evidence references.
6. **Report to the user** in their language: outcome first, numbers in a small table, the
   decisions taken, what comes next. Keep the mechanics in the log.
7. **Record reusable findings** with their evidence and fix when they affect later work.

### Coordinator review and verdict

The coordinator owns acceptance. Another worker may help verify, but the coordinator assesses
that report and decides. Review research and design conclusions as well as code; a confident
report is not evidence.

- **Evidence matches the claim.** Inspect the diff, source, logs, test output, or live
  observations, including the revision and environment tested. Separate observations,
  inferences, and assumptions. One successful probe does not prove a whole lifecycle. Ask for
  missing evidence or narrow the claim; do not quietly narrow the deliverable.
- **Fits the goal and plan.** Compare the result with the user's objective, latest steering,
  plan, and acceptance criteria. Find omitted requirements, unauthorized scope changes, and
  invented prerequisites. A worker's preferred approach does not redefine the goal; if the
  evidence justifies a new plan, record why before assigning dependent work.
- **Necessary complexity only.** Challenge each added abstraction, setting, dependency,
  fallback, and operational step; each should answer a concrete requirement or an observed
  failure. Prefer the smaller solution that meets the criteria. Do not demand extra tests just
  to make the review look thorough.
- **Correct and compatible.** Check the behavior and failure paths the brief cares about,
  consistency with existing contracts, and compatibility with other units. Resolve
  contradictory findings before accepting either.
- **Fix proven, no regression.** Accept a fix only with evidence on both sides: the defect
  reproduces on the old version and is gone on the new one, and neighbouring cases the change
  must not touch behave as before. For code, that is a regression test that fails on the
  parent commit plus the existing suite. For anything a model reads or decides (a prompt, a
  tool description, a classifier threshold, a harness rule that changes what the model sees),
  it is a real-model eval over three sets: cases that reproduce the defect on the old text,
  the same cases passing on the new text, and neighbour cases that must not change. At source
  review, a fix without the regression test or eval cases gets Rework; the before-and-after
  results are required by the §8 check that covers the fix, and a "the fix works" without the
  baseline reproduction or the neighbour cases does not pass that check.
- **Contract consumers updated.** When the diff changes a contract (brief part 3), grep for the
  old value across the repository, not only the worker's module, and confirm every suite that
  pinned it changed in the same change. Suites that run only late in the pipeline (acceptance
  or release-gate suites) are where a change that is green in its own module fails later.
- **User impact before release.** For every gap or "left out" item a worker reports, and every
  gap the review finds, answer: must this be fixed before the change reaches users, people or
  agent harnesses driving the product? A gap that breaks a documented contract on a path a user
  will take (a callback that never fires, a wait that returns before the client's own timeout,
  an exit code a script cannot branch on) is fixed before release, in the same change. A gap
  that can wait is listed with evidence: which path it affects, how a user would notice, and
  what they can do meanwhile. "Filed as a follow-up" without that evidence is not a verdict.

Give one explicit verdict, scaled to the task:

- **Accept:** name the stage (source accepted for integration, milestone check passed, or
  final verification passed), the evidence for it, and the checks still deferred under §8.
  Required code fixes block source acceptance; missing final evidence blocks release.
- **Rework:** send the same worker the discrepancy, the required change or evidence, and the
  condition for acceptance. Review the revised artifact against those points before changing
  the verdict; do not pass on the worker's assurance as your own conclusion.

**Test parallel units together before trusting either.** Two units that each pass alone can
fail together, most often through a shared fake or a shared field whose meaning one of them
changed. Once accepted units are together in the tree, run the union of their test packages at
the milestone check (§8) before opening the PR, and treat a fake's behaviour as part of the
contract the briefs fix.

## 6. Handling workers

### Research problems before concluding

This applies to the coordinator and every worker. When a problem appears, gather the local
facts and search for prior work before naming a cause, ruling out an approach, or choosing a
fix. A familiar symptom is a hypothesis, not a conclusion.

- **Search the actual problem:** the error text, component, version, environment, and
  constraints. Read upstream issues and discussions, official docs, maintainer responses, and
  relevant papers, including later corrections, not just snippets. Keep private data and
  credentials out of public queries.
- **Weigh the evidence.** Tell apart a proposed idea, a maintainer's recommendation, and a
  workaround with independent adoption reports. One comment or one popular post is not
  consensus. Check that the same mechanism and version apply here.
- **Choose with that context.** Compare established fixes and accepted workarounds before
  inventing a custom mechanism. Explain why the choice fits our constraints, its tradeoffs,
  and what remains uncertain. For a temporary workaround, state its limits and when to remove
  it.
- **Keep research bounded and shared.** Stop when the evidence supports a choice or further
  searches add nothing. Share findings so other workers can reuse them. If nothing relevant
  turns up, or browsing is unavailable, say what was searched and label the next step a
  hypothesis. Research does not grant permission to change scope or shared systems.

### Check in after 15 minutes without updates

- **The coordinator owns a timer per task.** At launch, record `last_activity_at` (UTC) and set
  `next_check_at` 15 minutes later. Refresh both on each worker message, new output, or
  observed progress. Another worker's activity does not reset this task's timer.
- **Wake independently of workers.** Use the harness's scheduled wake-up if it has one;
  otherwise keep a supervision loop with bounded waits of at most 60 seconds, checking the
  clock and worker updates between waits. Do not end the coordinating turn with tasks running
  and no active supervision; a promise to check later is not a timer.
- **At 15 minutes of silence, inspect.** Native worker: its status, recent messages, and
  current tool work; ask for a progress or blocker report if unclear. CLI worker: the process, recent stdout and stderr,
  child processes, and any pending test or permission wait. Log what you observed.
- **Intervene on a problem.** Fix an authorized dependency or permission setup, correct the
  brief, or interrupt a stuck operation. If the worker cannot recover, keep its artifacts and
  take over or reassign the unit after confirming the old work has stopped. Handle an exited
  or failed process as soon as you see it.
- **Silence alone is not failure.** If a long operation is healthy, set `next_check_at` 15
  minutes ahead without changing `last_activity_at`. If unsure, ask for a report and set a
  shorter follow-up. Repeated output without progress also needs a look. Inspecting a task or
  messaging it does not count as worker activity.

### Shared machine load

When workers, CI runners, and test environments share one machine, overload produces failures
that look like defects: cancelled CI runs, package test timeouts, failing timing assertions,
and restarting local services. Each costs a rerun.

- **Read the load before every dispatch and every merge**: the 1-minute load average from
  `uptime`, and the core count from `nproc` (Linux) or `sysctl -n hw.ncpu` (macOS). Above
  about twice the core count, dispatch nothing new and merge nothing; wait for
  running work to finish.
- **A PR push is a CI run.** If CI runs on the same machine, open or update the PR after the
  wave's final verification, not while workers are compiling and testing. While a CI run is
  in progress, do not start a new coding wave, a local full suite, or a performance
  measurement.
- **One heavy consumer per resource at a time:** at most one worker building a large external
  tree, one benchmark environment, and no benchmark during a CI run. Say in each brief which
  of these the unit may use and when.
- **Timing results measured under load are provisional.** Record the load average next to any
  timing result, and rerun a timing-sensitive check on a quiet machine before treating its
  failure as a defect or its pass as evidence.

### Wait loops, monitors, and polls

- **Know the shell your monitor runs in.** Some harness monitor tools run zsh, where an
  unquoted `$list` is not split into words and bash-specific syntax behaves differently, so a watch over several
  workers reports them all "exited" at once. Name the workers literally (`for n in a b c`) and
  record each exit with a marker file. Re-arm an expiring monitor while the watched process is
  alive.
- **Read CI check state correctly.** In `gh pr view --json statusCheckRollup`, a check run
  that is still running has an empty `conclusion`; read `status` when `conclusion` is empty.
  A commit status entry has neither field and reports in `state` (`PENDING` while running).
  Decide "all passed" over every entry (each check run `SUCCESS`, `SKIPPED`, or `NEUTRAL`, each commit
  status `SUCCESS`), not by comparing a joined string.
- **Merge only after every check has finished.** Merging while a check is queued skips that
  gate even if it later passes.

### Stuck tasks and orphans

- **Sweep at every check-in and before every final report:** background tasks and monitors,
  detached CLI processes (their PID files), test pods, port forwards, and worktrees of finished
  units. Name the unit that still needs each one; stop or remove anything without an owner.
- **A task that outlived its purpose is an orphan:** a wait loop whose condition can no longer
  come true, a monitor for an exited process, a poll for a closed PR, a port forward for a
  finished probe. Stop it when you notice it.
- **Handle a stuck task; do not wait on it.** No progress across two consecutive check-ins
  (same log size, same files, no working child process) means inspect what it is blocked on,
  then unblock it, restart it with the cause fixed, or stop it and record why. Rerun a
  cancelled or timed-out CI run once after the load is down; a second failure is real.
- **Leaked test processes count.** Look for processes from earlier test runs that outlived
  their parent: servers, browsers, or fixtures the repository's tests start
  (`ps -eo pid,ppid,etime,args` lists them with their parent and age). Stop the ones this
  session's runs started and report the leaking test; ask the user before stopping any other
  process.

### Recovery and ownership

- A watchdog **"stalled" notice is not proof of failure.** Inspect output and status first. Do
  not launch a replacement while the original still runs, and never select "the latest
  session" when several run in parallel.
- **Reuse a worker for follow-ups on its own work**; it keeps its context. Use a new worker or
  session only for a new unit.
- When a worker returns a design decision, **decide it**; do not bounce it back as a question.
- **Workers never write to shared systems** (trackers, tags, production, shared staging, pull
  requests). The coordinator makes such writes once, from verified facts. A worker that needs
  one reports the exact content.
- If you find yourself doing a worker's task while it runs, stop: either the brief was wrong
  (fix it and resume the worker) or the task was yours.

## 7. Anti-patterns

- Delegating an obvious simple task, or assigning workers before gathering context and
  forming a plan.
- Launching without an explicit model.
- Letting a worker integrate its own work (merge, tag, deploy, publish).
- Accepting a report's summary or its passing tests without inspecting the artifact, the
  evidence coverage, and the fit with the user's goal; integrating without a verdict.
- A brief that leaves out the constraints because "the agent knows the repo".
- Concurrent edits to the same file; recursive delegation; deleting unreviewed work.
- A worktree, pushed branch, CI run, or PR per unit when the units' files are disjoint; any
  git write by a worker in the shared checkout.
- A credential in a brief or message.
- Asking the user a question a worker's report already answered.
- Dispatching a coding wave, opening a PR, or starting a measurement while the machine is
  overloaded or a CI run is in progress on the same machine; leaving a monitor, port forward, test pod, or
  finished worktree without an owner.
- Running checks as a gate per worker, treating a handoff as a milestone, or running full
  validation before all milestones are code complete.
- A decrypted secret in a file or in worker output; a build binary in a commit; a changed
  interface merged without a repository-wide grep for its callers.
- Opening the PR without running the accepted units' combined tests.

## 8. Pace: code complete first, a minimum check per milestone, verify together

Finish the planned code across the whole project first. Verification has two fixed points:
one minimum check per completed milestone, and one coordinated full verification after every
milestone is code complete. Do not run the full delivery checklist per worker or per milestone.

1. **Implement to code complete.** Workers write the implementation, test sources,
   contract-consumer updates, and needed generated code. Code complete means the planned
   source changes are present and reviewed, not that tests passed. Workers do not run build,
   static analysis, tests, lint, or format sweeps before handing back a unit; record those checks as
   deferred. A narrow diagnostic to resolve an implementation blocker is allowed; record its
   purpose and result and do not grow it into a validation suite.
2. **Check once at each milestone boundary.** Define milestones in the plan before dispatch;
   a worker handoff is not a milestone. When all of a milestone's source is integrated, run
   the affected build and static checks plus the smallest tests that exercise the milestone's
   contract over the combined changes. Fix a failure, rerun the affected check, and continue.
   Do not run full regression suites, race sweeps, lint, broad formatting, staging, or
   end-to-end acceptance at this boundary.
3. **Verify together once all code is complete.** Run formatting on changed files, the full
   relevant tests and regression suites, race checks where relevant, lint, and the project's
   end-to-end or staging acceptance, over the combined project including contracts shared
   across units. A fix ships with its no-regression evidence (§5). Run each gate unpiped, or
   check `PIPESTATUS`: a gate piped into `tail` or `grep` inside an `&&` chain reports the
   filter's exit status, not the gate's. Fix findings and rerun the affected checks; repeat
   broader checks only when the fixes or open evidence call for it. "Once" means one planned
   phase, not permission to leave a failed check unresolved. Code complete alone never means
   verified, releasable, or done.
4. **Do shared work once.** Give regeneration and integration work to the last dependent unit
   or the coordinator when earlier units would repeat it. Reuse evidence for unchanged code.
   Keep milestones and verification owners in the plan so later workers do not redo checks.
   Stop test processes and clean test data after checks; preserve reports and integrated
   commits before removing worktrees.
5. **Apply supported lint fixes automatically in the final phase.** Run the linter's autofix
   on the project's changed files only, never an unrestricted repository-wide autofix. Review
   the resulting diff, fix the remaining findings by hand, rerun affected tests when a fix
   changes behavior, and finish with the repository's full lint gate.
6. **Use the repository's tools for mechanical work.** Prefer existing generators, codemods,
   formatters, autofixes, and scripts to reproducing their output by hand, then inspect the
   diff. Automation follows the phase schedule above.

An explicit instruction from the user to validate earlier overrides this schedule; record the
exception and its scope. Do not infer an early full-verification gate from a worker's
preference or a generic review checklist. Very simple tasks remain direct work under §0.
