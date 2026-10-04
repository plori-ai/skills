---
name: root-cause-debugging
description: Diagnose production incidents, recurring bugs, teardown failures, race conditions, and misleading timeout symptoms by reconstructing evidence, asking three closing why questions, checking current primary-source practices, and designing fixes that remove the causal mechanism instead of masking it. Use for “find the root cause,” “look into this bug,” “why did this recur,” incident recovery plus follow-up work, and postmortem-quality debugging. Do not use for a straightforward known fix that needs no diagnosis.
---

# Root Cause Debugging

Find the earliest broken invariant, restore service safely when authorized, and leave behind a repair that prevents the same failure class. Do not stop at the last timeout or error wrapper.

## Evidence First

Build one timestamped causal timeline from the narrowest useful evidence:

- the user's symptom and exact affected identity;
- application logs and metrics;
- orchestrator events and object history;
- runtime, storage, network, or dependency state below the application;
- the code paths that create, retry, clean up, and recover that state.

Prefer live read-only inspection before mutation. Preserve exact IDs, UIDs, nodes, versions, and timestamps, but never expose credentials or unrelated user data. Treat source comments and runbooks as hypotheses until live behavior and code agree.

Classify each observation explicitly as one of:

- **symptom**: what the user saw;
- **direct cause**: the failed operation immediately producing it;
- **amplifier**: retry, fallback, cleanup, or stale state that made impact longer or wider;
- **contributor**: suspicious evidence that may matter but is not yet causally proven;
- **root mechanism**: the violated ownership, lifecycle, state-authority, or recovery invariant that permits recurrence.

Do not promote correlation to cause. Falsify the leading explanation against at least one independent signal before accepting it.

## Recovery Is Not the Fix

When recovery is requested, choose the smallest action that removes the confirmed blocker:

1. Resolve the exact target and inspect neighboring healthy workloads.
2. State the expected effect, blast radius, and stopping condition.
3. Quarantine scheduling or retries when they could recreate the failure during recovery.
4. Mutate only after the user has authorized that class of production action.
5. Verify both the user's path and the lower-level invariant; then remove the quarantine.

Never weaken a safety fence merely to make recovery faster. For exclusive storage, locks, leases, or fencing tokens, do not force takeover while the incumbent may still perform I/O.

Record what the recovery proves. A restart that clears state proves recoverability, not root cause and not permanence.

## Three Closing Whys

After reconstructing the timeline, work down these three causal questions in order, answering each with evidence and making that answer the premise of the next.

1. **Why did the user-visible operation fail?** Trace past wrapper errors and timeouts to the first failed subsystem operation or broken invariant.
2. **Why did that failure persist or become user-visible instead of being contained?** Examine ownership, retries, fallbacks, teardown, reconciliation, leases, duplicated state, and which component was treated as authoritative.
3. **Why did the system permit or miss that unsafe state?** Examine design assumptions, version behavior, tests, failure injection, observability, and operational recovery. This answer should identify the repairable system mechanism.

If an answer is still “because component X timed out,” it is not closed. Ask what X was waiting for, which state disagreed, who owned cleanup, and what terminal signal was missing. Stop deepening when the remaining cause is external and well evidenced; distinguish the upstream trigger from the product-owned containment gap.

## Current Best Practice Check

For behavior that can change with releases or operations, search current primary sources: official documentation, source code, release notes, maintainers' issues, Kubernetes enhancement/design material, or relevant standards. Compare the exact deployed versions and configuration with current behavior. Use secondary incident reports only as corroboration.

Look specifically for lifecycle guidance relevant to the mechanism, such as:

- controller reconciliation and finalizers rather than assuming API deletion means physical cleanup;
- idempotent teardown with a positive completion signal;
- fencing and single-writer leases;
- PID 1 signal forwarding and child reaping;
- runtime state reconciliation after shim or node failure;
- bounded retries with an actionable terminal state;
- failure-injection tests for kill, node loss, partial deletion, and state disagreement.

State whether an upstream change is a confirmed fix, a related mitigation, or merely worth testing. Never claim that a version bump fixes the incident without reproducing the failure before and after.

## Design the Durable Repair

Prefer one fix at the layer that owns each broken invariant. A durable repair usually needs no more than these three concerns:

1. **Safety:** prevent a second actor from proceeding while ownership or cleanup is uncertain.
2. **Liveness:** provide a bounded, observable path that confirms cleanup or escalates to safe recovery.
3. **Verification:** add a regression or failure-injection test plus an alert on the earliest actionable signal.

Every proposed change must name the causal edge it closes. Remove redundant fallbacks that turn one fault into repeated work. Do not add timers to hide an unbounded state, lower a lease TTL without analyzing its other safety purpose, or duplicate validation across layers.

Before calling the diagnosis complete, state:

- what is proven;
- what remains uncertain;
- why the proposed mechanism handles both the observed incident and its close variants;
- what would falsify the diagnosis;
- how recovery and regression prevention will be verified.

## Tracking Work

When the user asks for issues, follow the repository's configured tracker. Split work only when items have different owners, rollout risks, or independently testable outcomes. Do not create one issue per log symptom.

Each issue should include the incident evidence, violated invariant, scope, non-goals, safe rollout, and acceptance tests. Include a reproduction or failure-injection test that demonstrates the old failure and proves bounded recovery. Link related upstream evidence without delegating correctness to it.
