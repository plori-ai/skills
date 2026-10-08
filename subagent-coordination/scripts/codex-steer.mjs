#!/usr/bin/env node
// codex-steer: run a Codex worker that accepts more messages while it works.
//
// `codex exec` reads its prompt once and cannot take input mid-run. This script drives
// `codex app-server` over stdio instead, so a coordinator can steer the running turn
// (`turn/steer`), queue a follow-up turn, or interrupt, without killing the worker.
//
//   node codex-steer.mjs run --cwd DIR --out DIR [--model M] [--sandbox MODE]
//        [--approval POLICY] [--resume THREAD_ID] [--linger SECONDS]
//        [--codex PATH] [-c key=value ...] < brief.md
//   node codex-steer.mjs send DIR [--interrupt] [--wait SECONDS] (TEXT | - < file)
//   node codex-steer.mjs interrupt DIR
//   node codex-steer.mjs status DIR
//
// Files in the output directory:
//   pid, state.json   wrapper PID; thread ID, active turn, status, last activity (UTC)
//   events.jsonl      every app-server message except streaming deltas
//   report.md         final agent message of the most recent turn
//   turns/N.md        final agent message of turn N
//   steer.log         one line per delivered, queued, or refused message
//   inbox/            messages waiting for the worker; inbox/acks/ holds delivery results
//   codex-stderr.log  app-server stderr
//   exit              "exit N" once the wrapper has stopped
//
// Exit codes: 0 last turn completed, 1 last turn failed, 2 interrupted, 3 startup or
// protocol error. Requires Node 18+ and a Codex CLI with `app-server` and `turn/steer`.

import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import crypto from "node:crypto";

const VERSION = "0.1.0";
const POLL_MS = 300;

function die(msg, code = 3) {
  process.stderr.write(`codex-steer: ${msg}\n`);
  process.exit(code);
}

function now() {
  return new Date().toISOString();
}

function readStdin() {
  try {
    return fs.readFileSync(0, "utf8");
  } catch {
    return "";
  }
}

function writeAtomic(file, data) {
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, data);
  fs.renameSync(tmp, file);
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

function alive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return err.code === "EPERM";
  }
}

function parseArgs(argv, spec) {
  const out = { _: [], c: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "-c" || a === "--config") {
      out.c.push(argv[++i]);
    } else if (a.startsWith("--")) {
      const key = a.slice(2);
      if (spec.flags.includes(key)) out[key] = true;
      else if (spec.values.includes(key)) {
        if (i + 1 >= argv.length) die(`missing value for ${a}`);
        out[key] = argv[++i];
      } else die(`unknown option ${a}`);
    } else out._.push(a);
  }
  return out;
}

// ---------------------------------------------------------------- client commands

function enqueue(dir, kind, text) {
  const inbox = path.join(dir, "inbox");
  if (!fs.existsSync(inbox)) die(`${inbox} does not exist; is ${dir} a codex-steer output directory?`);
  const id = `${Date.now()}-${crypto.randomBytes(3).toString("hex")}`;
  writeAtomic(path.join(inbox, `${id}.json`), JSON.stringify({ id, kind, text, at: now() }));
  return id;
}

async function waitAck(dir, id, seconds) {
  const ackFile = path.join(dir, "inbox", "acks", `${id}.json`);
  const deadline = Date.now() + seconds * 1000;
  for (;;) {
    const ack = readJson(ackFile);
    if (ack) return ack;
    const state = readJson(path.join(dir, "state.json"));
    if (!alive(state?.pid) && !fs.existsSync(ackFile)) {
      return { status: "undelivered", reason: "worker is not running; message left in inbox" };
    }
    if (Date.now() > deadline) return { status: "pending", reason: `no ack after ${seconds}s` };
    await new Promise((r) => setTimeout(r, 200));
  }
}

async function cmdSend(argv) {
  const opts = parseArgs(argv, { flags: ["interrupt"], values: ["wait"] });
  const [dir, ...rest] = opts._;
  if (!dir) die("usage: send DIR [--interrupt] [--wait SECONDS] (TEXT | -)");
  let text = rest.join(" ");
  if (text === "-" || text === "") text = readStdin();
  if (!text.trim()) die("empty message");
  if (opts.interrupt) enqueue(dir, "interrupt", "");
  const id = enqueue(dir, "message", text);
  const ack = await waitAck(dir, id, Number(opts.wait ?? 30));
  process.stdout.write(`${JSON.stringify({ id, ...ack })}\n`);
  process.exit(["steered", "started", "queued"].includes(ack.status) ? 0 : 1);
}

async function cmdInterrupt(argv) {
  const [dir] = argv;
  if (!dir) die("usage: interrupt DIR");
  const id = enqueue(dir, "interrupt", "");
  const ack = await waitAck(dir, id, 30);
  process.stdout.write(`${JSON.stringify({ id, ...ack })}\n`);
  process.exit(ack.status === "interrupted" || ack.status === "idle" ? 0 : 1);
}

function cmdStatus(argv) {
  const [dir] = argv;
  if (!dir) die("usage: status DIR");
  const state = readJson(path.join(dir, "state.json")) ?? {};
  let pending = 0;
  try {
    pending = fs.readdirSync(path.join(dir, "inbox")).filter((f) => f.endsWith(".json")).length;
  } catch {}
  const exit = fs.existsSync(path.join(dir, "exit")) ? fs.readFileSync(path.join(dir, "exit"), "utf8").trim() : null;
  process.stdout.write(`${JSON.stringify({ ...state, alive: alive(state.pid), pendingInbox: pending, exit })}\n`);
}

// ---------------------------------------------------------------- worker

async function cmdRun(argv) {
  const opts = parseArgs(argv, {
    flags: [],
    values: ["cwd", "out", "model", "sandbox", "approval", "resume", "linger", "codex", "effort"],
  });
  if (!opts.cwd || !opts.out) die("run needs --cwd DIR and --out DIR");
  const cwd = path.resolve(opts.cwd);
  const out = path.resolve(opts.out);
  const linger = Number(opts.linger ?? 0) * 1000;
  const brief = readStdin();
  if (!brief.trim() && !opts.resume) die("empty brief on stdin");

  const inbox = path.join(out, "inbox");
  fs.mkdirSync(path.join(inbox, "acks"), { recursive: true });
  fs.mkdirSync(path.join(inbox, "done"), { recursive: true });
  fs.mkdirSync(path.join(out, "turns"), { recursive: true });
  for (const f of ["exit"]) fs.rmSync(path.join(out, f), { force: true });
  fs.writeFileSync(path.join(out, "pid"), `${process.pid}\n`);

  const events = fs.createWriteStream(path.join(out, "events.jsonl"), { flags: "a" });
  const steerLog = fs.createWriteStream(path.join(out, "steer.log"), { flags: "a" });
  const logSteer = (line) => steerLog.write(`${now()} ${line}\n`);

  const state = {
    pid: process.pid,
    threadId: null,
    activeTurnId: null,
    status: "starting",
    turns: 0,
    lastTurnStatus: null,
    lastActivityAt: now(),
  };
  const saveState = () => writeAtomic(path.join(out, "state.json"), JSON.stringify(state, null, 2));
  saveState();

  const codexArgs = [];
  for (const c of opts.c) codexArgs.push("-c", c);
  if (opts.effort) codexArgs.push("-c", `model_reasoning_effort=${opts.effort}`);
  codexArgs.push("app-server");
  const child = spawn(opts.codex ?? "codex", codexArgs, {
    cwd,
    stdio: ["pipe", "pipe", fs.openSync(path.join(out, "codex-stderr.log"), "a")],
  });
  child.on("error", (err) => finish(3, `cannot start codex: ${err.message}`));
  child.on("exit", (code, signal) => {
    if (!finished && !stopping) finish(3, `app-server exited (code ${code}, signal ${signal})`);
  });

  let nextId = 1;
  const waiting = new Map();
  function request(method, params) {
    const id = nextId++;
    child.stdin.write(`${JSON.stringify({ id, method, params })}\n`);
    return new Promise((resolve, reject) => waiting.set(id, { resolve, reject, method }));
  }
  function notify(method, params) {
    child.stdin.write(`${JSON.stringify(params === undefined ? { method } : { method, params })}\n`);
  }
  function reply(id, body) {
    child.stdin.write(`${JSON.stringify({ id, ...body })}\n`);
  }

  // Per-turn bookkeeping.
  const lastAgentMessage = new Map();
  let turnDone = null; // resolves when the active turn completes
  let pending = []; // messages to send as the next turn
  let finished = false;
  let stopping = false;

  const seenTurns = new Set();
  let interruptingTurn = null;
  function onTurnStarted(turn) {
    if (seenTurns.has(turn.id)) return;
    seenTurns.add(turn.id);
    state.activeTurnId = turn.id;
    state.status = "running";
    state.turns += 1;
    saveState();
  }

  function onTurnCompleted(turn) {
    const text = lastAgentMessage.get(turn.id) ?? "";
    let body = text;
    if (turn.status !== "completed") {
      const detail = turn.error ? `: ${turn.error.message ?? JSON.stringify(turn.error)}` : "";
      body += `${text ? "\n\n" : ""}[turn ${turn.status}${detail}]`;
    }
    writeAtomic(path.join(out, "turns", `${state.turns}.md`), `${body}\n`);
    writeAtomic(path.join(out, "report.md"), `${body}\n`);
    state.lastTurnStatus = turn.status;
    if (turn.status === "completed") state.lastError = null;
    if (state.activeTurnId === turn.id) state.activeTurnId = null;
    state.status = "idle";
    saveState();
    if (turnDone) turnDone.resolve(turn);
  }

  const rl = readline.createInterface({ input: child.stdout });
  rl.on("line", (line) => {
    if (!line.trim()) return;
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      events.write(`${JSON.stringify({ unparsed: line })}\n`);
      return;
    }
    state.lastActivityAt = now();
    const method = msg.method ?? "";
    if (!/delta$/i.test(method)) events.write(`${line}\n`);

    if (msg.id !== undefined && method) {
      // Server -> client request. The worker runs unattended, so decline approvals
      // (the agent continues and reports the blocker) and refuse anything else.
      if (/requestApproval$/.test(method)) {
        logSteer(`declined ${method}`);
        reply(msg.id, { result: { decision: "decline" } });
      } else {
        logSteer(`refused server request ${method}`);
        reply(msg.id, { error: { code: -32601, message: `codex-steer does not handle ${method}` } });
      }
      return;
    }
    if (msg.id !== undefined) {
      const w = waiting.get(msg.id);
      if (!w) return;
      waiting.delete(msg.id);
      if (msg.error) w.reject(Object.assign(new Error(msg.error.message ?? "error"), { rpc: msg.error }));
      else w.resolve(msg.result);
      return;
    }
    const p = msg.params ?? {};
    if (method === "turn/started" && p.turn) onTurnStarted(p.turn);
    else if (method === "turn/completed" && p.turn) onTurnCompleted(p.turn);
    else if (method === "error" && p.error) {
      state.lastError = { message: p.error.message, details: p.error.additionalDetails ?? null, willRetry: p.willRetry ?? null, at: now() };
      saveState();
    } else if (method === "item/completed" && p.item?.type === "agentMessage") {
      lastAgentMessage.set(p.turnId, p.item.text);
    }
  });

  function finish(code, reason) {
    if (finished) return;
    finished = true;
    if (reason) process.stderr.write(`codex-steer: ${reason}\n`);
    state.status = "exited";
    state.activeTurnId = null;
    saveState();
    fs.writeFileSync(path.join(out, "exit"), `exit ${code}\n`);
    try {
      child.stdin.end();
      child.kill("SIGTERM");
    } catch {}
    events.end();
    steerLog.end(() => process.exit(code));
  }

  const textInput = (text) => [{ type: "text", text, text_elements: [] }];

  async function startTurn(texts) {
    turnDone = Promise.withResolvers ? Promise.withResolvers() : deferred();
    const res = await request("turn/start", {
      threadId: state.threadId,
      input: texts.flatMap(textInput),
    });
    // turn/started normally arrives first, but do not depend on the order.
    onTurnStarted(res.turn);
    return res.turn.id;
  }

  // ---------------------------------------------------------- inbox handling
  function ack(item, body) {
    writeAtomic(path.join(inbox, "acks", `${item.id}.json`), JSON.stringify({ ...body, at: now() }));
    fs.renameSync(item.file, path.join(inbox, "done", path.basename(item.file)));
  }

  function takeInbox() {
    let names;
    try {
      names = fs.readdirSync(inbox).filter((f) => f.endsWith(".json")).sort();
    } catch {
      return [];
    }
    const items = [];
    for (const name of names) {
      const file = path.join(inbox, name);
      const msg = readJson(file);
      if (msg) items.push({ ...msg, file });
    }
    return items;
  }

  let draining = false;
  async function drainInbox() {
    if (draining || finished || !state.threadId) return;
    draining = true;
    try {
      for (const item of takeInbox()) {
        if (item.kind === "interrupt") {
          if (state.activeTurnId) {
            try {
              interruptingTurn = state.activeTurnId;
              await request("turn/interrupt", { threadId: state.threadId, turnId: state.activeTurnId });
              logSteer(`interrupted turn ${state.activeTurnId}`);
              ack(item, { status: "interrupted" });
            } catch (err) {
              ack(item, { status: "failed", reason: err.message });
            }
          } else ack(item, { status: "idle" });
          continue;
        }
        if (state.activeTurnId && state.activeTurnId !== interruptingTurn && pending.length === 0) {
          const turnId = state.activeTurnId;
          try {
            await request("turn/steer", {
              threadId: state.threadId,
              input: textInput(item.text),
              expectedTurnId: turnId,
            });
            logSteer(`steered turn ${turnId}: ${item.text.slice(0, 120).replace(/\n/g, " ")}`);
            ack(item, { status: "steered", turnId });
            continue;
          } catch (err) {
            // No active turn (it just ended), a review/compact turn, or a turn-id race:
            // deliver the message as the next turn instead.
            logSteer(`steer refused (${err.message}); queued for next turn`);
          }
        }
        if (state.activeTurnId) {
          pending.push(item.text);
          logSteer(`queued for next turn: ${item.text.slice(0, 120).replace(/\n/g, " ")}`);
          ack(item, { status: "queued" });
        } else {
          pending.push(item.text);
          ack(item, { status: "started" });
          logSteer(`starting turn with: ${item.text.slice(0, 120).replace(/\n/g, " ")}`);
        }
      }
    } finally {
      draining = false;
    }
  }

  // ---------------------------------------------------------- main sequence
  const stop = (sig) => async () => {
    if (stopping) return;
    stopping = true;
    logSteer(`received ${sig}`);
    if (state.activeTurnId) {
      try {
        await Promise.race([
          request("turn/interrupt", { threadId: state.threadId, turnId: state.activeTurnId }),
          new Promise((r) => setTimeout(r, 3000)),
        ]);
      } catch {}
    }
    finish(2, `stopped by ${sig}`);
  };
  process.on("SIGTERM", stop("SIGTERM"));
  process.on("SIGINT", stop("SIGINT"));

  try {
    await request("initialize", {
      clientInfo: { name: "codex-steer", title: "codex-steer", version: VERSION },
      capabilities: null,
    });
    notify("initialized");
    const threadParams = {
      cwd,
      ...(opts.model && { model: opts.model }),
      sandbox: opts.sandbox ?? "workspace-write",
      approvalPolicy: opts.approval ?? "never",
    };
    const res = opts.resume
      ? await request("thread/resume", { threadId: opts.resume, ...threadParams })
      : await request("thread/start", threadParams);
    state.threadId = res.thread.id;
    state.model = res.model;
    state.status = "idle";
    saveState();
    fs.writeFileSync(path.join(out, "thread_id"), `${state.threadId}\n`);
  } catch (err) {
    finish(3, `startup failed: ${err.message}`);
    return;
  }

  const poller = setInterval(() => drainInbox().catch((e) => logSteer(`inbox error: ${e.message}`)), POLL_MS);

  if (brief.trim()) pending.push(brief);
  for (;;) {
    await drainInbox();
    if (pending.length === 0 && linger > 0) {
      const deadline = Date.now() + linger;
      while (pending.length === 0 && Date.now() < deadline && !finished) {
        await new Promise((r) => setTimeout(r, POLL_MS));
        await drainInbox();
      }
    }
    if (pending.length === 0 || finished) break;
    const texts = pending;
    pending = [];
    try {
      await startTurn(texts);
    } catch (err) {
      logSteer(`turn/start failed: ${err.message}`);
      clearInterval(poller);
      finish(3, `turn/start failed: ${err.message}`);
      return;
    }
    await turnDone.promise;
    // Let in-flight steer requests settle so a refused steer lands in `pending`.
    while (draining) await new Promise((r) => setTimeout(r, 50));
  }
  clearInterval(poller);
  const code = { completed: 0, failed: 1, interrupted: 2 }[state.lastTurnStatus] ?? 3;
  finish(code);
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((a, b) => ((resolve = a), (reject = b)));
  return { promise, resolve, reject };
}

const [cmd, ...rest] = process.argv.slice(2);
const commands = { run: cmdRun, send: cmdSend, interrupt: cmdInterrupt, status: cmdStatus };
if (!commands[cmd]) {
  process.stderr.write("usage: codex-steer.mjs (run|send|interrupt|status) ...  (see header comment)\n");
  process.exit(3);
}
await commands[cmd](rest);
