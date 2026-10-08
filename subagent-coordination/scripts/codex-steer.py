#!/usr/bin/env python3
"""codex-steer: run many Codex workers that accept messages while they work.

`codex exec` reads its prompt once and starts a full Codex process per worker. This tool runs
every worker as a thread inside ONE shared `codex app-server` process, owned by one small
daemon, so N workers cost one app-server plus a few MB each. A coordinator can steer a running
turn (`turn/steer`), interrupt and redirect it, queue a follow-up turn, or resume the thread.

    codex-steer.py run --cwd DIR --out DIR [--model M] [--sandbox MODE] [--approval POLICY]
                       [--effort LEVEL] [--resume THREAD_ID] [--linger SECONDS]
                       [-c key=value ...] [--wait] < brief.md
    codex-steer.py send DIR [--interrupt] (TEXT | -)
    codex-steer.py interrupt DIR
    codex-steer.py stop DIR                 # interrupt and end the task
    codex-steer.py wait [--any] [--timeout SECONDS] DIR...
    codex-steer.py status [DIR]             # one task, or every task in the pool
    codex-steer.py daemon (status | stop)

Every command takes --pool NAME (default "default", or $CODEX_STEER_POOL). The first `run`
starts the pool's daemon; it exits after --idle-exit seconds (default 300) with no task.
Flags for the shared app-server (--codex PATH, and `daemon start -c key=value` or
`run --daemon-config key=value`) apply only when that command starts the daemon. `run -c`
values are config for that worker's thread only.

Files in a task's output directory:
    state.json        thread ID, active turn, status (starting|running|idle|exited),
                      turns, lastTurnStatus, lastActivityAt, lastError
    events.jsonl      app-server notifications for this thread, without streaming deltas
    report.md         final agent message of the latest turn; turns/N.md for turn N
    steer.log         one line per delivered, queued, or refused message
    thread_id         for `run --resume`
    exit              "exit N" once the task has ended: 0 last turn completed, 1 failed,
                      2 interrupted or stopped, 3 startup or protocol error

Requires Python 3.8+ (stdlib only) and a Codex CLI whose app-server has `turn/steer`.
"""

import asyncio
import contextlib
import fcntl
import glob
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

VERSION = "0.2.0"
DELIVERED = ("steered", "queued", "started")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def die(msg, code=3):
    sys.stderr.write("codex-steer: %s\n" % msg)
    sys.exit(code)


def write_atomic(path, data):
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w") as f:
        f.write(data)
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def pool_paths(pool):
    base = os.environ.get("CODEX_STEER_DIR") or os.path.join(
        os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "codex-steer-%d" % os.getuid())
    os.makedirs(base, mode=0o700, exist_ok=True)
    p = os.path.join(base, pool)
    sock = p + ".sock"
    if len(sock.encode()) > 100:  # AF_UNIX path limit is about 104-108 bytes
        import hashlib
        sock = "/tmp/codex-steer-%d-%s.sock" % (os.getuid(), hashlib.sha1(sock.encode()).hexdigest()[:12])
    return {"sock": sock, "pid": p + ".pid", "log": p + ".log", "lock": p + ".lock"}


def parse_override(item):
    """Parse a `-c key=value` override into (key, JSON value); value is TOML when possible."""
    if "=" not in item:
        die("bad -c value %r; expected key=value" % item)
    key, raw = item.split("=", 1)
    try:
        import tomllib  # Python 3.11+
        return key.strip(), tomllib.loads("v = " + raw)["v"]
    except Exception:
        try:
            return key.strip(), json.loads(raw)
        except ValueError:
            return key.strip(), raw


def resolve_codex(path=None):
    """Find the native codex binary, skipping the npm Node shim (one fewer process)."""
    exe = path or shutil.which("codex")
    if not exe:
        raise RuntimeError("codex not found on PATH; pass --codex PATH")
    real = os.path.realpath(exe)
    env = {}
    with open(real, "rb") as f:
        is_script = f.read(2) == b"#!"
    if not is_script:
        return real, env
    # npm layout: <prefix>/node_modules/@openai/codex/bin/codex.js, native binary in the
    # platform package @openai/codex-<os>-<arch>/vendor/<triple>/bin/codex.
    pkg = os.path.dirname(os.path.dirname(real))
    roots = [os.path.join(pkg, "vendor"),
             os.path.join(pkg, "node_modules", "@openai", "codex-*", "vendor"),
             os.path.join(os.path.dirname(pkg), "codex-*", "vendor")]
    machine = platform.machine().lower()
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}.get(machine, machine)
    for root in roots:
        for cand in sorted(glob.glob(os.path.join(root, arch + "-*", "bin", "codex"))):
            if os.access(cand, os.X_OK):
                env["CODEX_MANAGED_BY_NPM"] = "1"
                env["CODEX_MANAGED_PACKAGE_ROOT"] = pkg
                return cand, env
    return real, env  # unknown wrapper: run it as is


# ------------------------------------------------------------------------------- daemon


class AppServer:
    """One `codex app-server` over stdio, shared by every task in the pool."""

    def __init__(self, daemon, codex, overrides):
        self.daemon = daemon
        self.codex = codex
        self.overrides = overrides
        self.proc = None
        self.next_id = 1
        self.waiting = {}
        self.ready = None

    async def ensure(self):
        if self.ready is None:
            self.ready = asyncio.ensure_future(self._start())
        try:
            await self.ready
        except Exception:
            self.ready = None
            raise

    async def _start(self):
        binary, extra_env = resolve_codex(self.codex)
        args = [binary]
        if not any(k == "thread_unload_delay_secs" for k, _ in self.overrides):
            # Ended tasks unsubscribe; unload their threads soon instead of after 30 minutes.
            args += ["-c", "thread_unload_delay_secs=10"]
        for k, v in self.overrides:
            args += ["-c", "%s=%s" % (k, v)]
        args.append("app-server")
        env = dict(os.environ, **extra_env)
        log = open(self.daemon.paths["log"] + ".codex", "ab")
        self.proc = await asyncio.create_subprocess_exec(
            *args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, env=env,
            limit=64 * 1024 * 1024)
        log.close()
        asyncio.ensure_future(self._read(self.proc))
        await self.request("initialize", {
            "clientInfo": {"name": "codex-steer", "title": "codex-steer", "version": VERSION},
            "capabilities": None})
        self._send({"method": "initialized"})

    def _send(self, msg):
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())

    def request(self, method, params):
        rid = self.next_id
        self.next_id += 1
        fut = asyncio.get_event_loop().create_future()
        self.waiting[rid] = fut
        self._send({"id": rid, "method": method, "params": params})
        return fut

    async def _read(self, proc):
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            method = msg.get("method")
            if "id" in msg and method:
                self._server_request(msg)
            elif "id" in msg:
                fut = self.waiting.pop(msg["id"], None)
                if fut and not fut.done():
                    if "error" in msg:
                        err = msg["error"] or {}
                        fut.set_exception(RuntimeError(err.get("message", "error")))
                    else:
                        fut.set_result(msg.get("result"))
            else:
                self.daemon.on_notification(method or "", msg.get("params") or {}, line)
        await proc.wait()
        for fut in self.waiting.values():
            if not fut.done():
                fut.set_exception(RuntimeError("app-server exited"))
        self.waiting.clear()
        if self.proc is proc:
            self.proc = None
            self.ready = None
            self.daemon.on_server_exit(proc.returncode)

    def _server_request(self, msg):
        # Workers run unattended: decline approvals (the agent continues and reports the
        # blocker) and refuse anything else.
        method = msg["method"]
        task = self.daemon.task_for_thread((msg.get("params") or {}).get("threadId"))
        if method.endswith("requestApproval"):
            if task:
                task.log("declined %s" % method)
            self._send({"id": msg["id"], "result": {"decision": "decline"}})
        else:
            if task:
                task.log("refused server request %s" % method)
            self._send({"id": msg["id"], "error": {"code": -32601, "message": "codex-steer does not handle %s" % method}})

    def stop(self):
        if self.proc and self.proc.returncode is None:
            with contextlib.suppress(Exception):
                self.proc.terminate()


class Task:
    def __init__(self, daemon, out, linger):
        self.daemon = daemon
        self.out = out
        self.linger = linger
        self.thread_id = None
        self.active_turn = None
        self.interrupting = None
        self.pending = []
        self.turns = 0
        self.seen_turns = set()
        self.last_agent = {}
        self.last_turn_status = None
        self.last_error = None
        self.status = "starting"
        self.exit_code = None
        self.last_activity = now()
        self.last_state_write = 0.0
        self.linger_handle = None
        self.waiters = []
        self.lock = asyncio.Lock()
        os.makedirs(os.path.join(out, "turns"), exist_ok=True)
        with contextlib.suppress(FileNotFoundError):
            os.remove(os.path.join(out, "exit"))
        self.events = open(os.path.join(out, "events.jsonl"), "ab")
        self.steer_log = open(os.path.join(out, "steer.log"), "a")
        self.save()

    def log(self, line):
        self.steer_log.write("%s %s\n" % (now(), line))
        self.steer_log.flush()

    def state(self):
        return {"out": self.out, "threadId": self.thread_id, "activeTurnId": self.active_turn,
                "status": self.status, "turns": self.turns, "pending": len(self.pending),
                "lastTurnStatus": self.last_turn_status, "lastActivityAt": self.last_activity,
                "lastError": self.last_error, "exit": self.exit_code, "pool": self.daemon.pool,
                "daemonPid": os.getpid()}

    def save(self):
        self.last_state_write = time.monotonic()
        write_atomic(os.path.join(self.out, "state.json"), json.dumps(self.state(), indent=2))

    # -- app-server events

    def on_notification(self, method, p, raw):
        self.last_activity = now()
        if not method.lower().endswith("delta"):
            self.events.write(raw if raw.endswith(b"\n") else raw + b"\n")
            self.events.flush()
        if method == "turn/started" and p.get("turn"):
            self.turn_started(p["turn"])
        elif method == "turn/completed" and p.get("turn"):
            self.turn_completed(p["turn"])
        elif method == "error" and p.get("error"):
            e = p["error"]
            self.last_error = {"message": e.get("message"), "details": e.get("additionalDetails"),
                               "willRetry": p.get("willRetry"), "at": now()}
            self.save()
        elif method == "item/completed" and (p.get("item") or {}).get("type") == "agentMessage":
            self.last_agent[p.get("turnId")] = p["item"].get("text", "")
        elif time.monotonic() - self.last_state_write > 5:
            self.save()

    def turn_started(self, turn):
        if turn["id"] in self.seen_turns:
            return
        self.seen_turns.add(turn["id"])
        self.active_turn = turn["id"]
        self.status = "running"
        self.turns += 1
        self.save()

    def turn_completed(self, turn):
        text = self.last_agent.pop(turn["id"], "")
        body = text
        if turn.get("status") != "completed":
            err = turn.get("error") or {}
            detail = (": " + (err.get("message") or json.dumps(err))) if err else ""
            body += ("\n\n" if text else "") + "[turn %s%s]" % (turn.get("status"), detail)
        write_atomic(os.path.join(self.out, "turns", "%d.md" % self.turns), body + "\n")
        write_atomic(os.path.join(self.out, "report.md"), body + "\n")
        self.last_turn_status = turn.get("status")
        if self.last_turn_status == "completed":
            self.last_error = None
        if self.active_turn == turn["id"]:
            self.active_turn = None
        self.status = "idle"
        self.save()
        asyncio.ensure_future(self.advance())

    # -- lifecycle

    async def start(self, params, brief, resume):
        server = self.daemon.server
        await server.ensure()
        res = await (server.request("thread/resume", dict(params, threadId=resume)) if resume
                     else server.request("thread/start", params))
        self.thread_id = res["thread"]["id"]
        self.daemon.by_thread[self.thread_id] = self
        write_atomic(os.path.join(self.out, "thread_id"), self.thread_id + "\n")
        self.status = "idle"
        if brief.strip():
            self.pending.append(brief)
        await self.advance()

    async def advance(self):
        """Start the next turn from pending messages, linger, or end the task."""
        async with self.lock:
            if self.exit_code is not None or self.active_turn:
                return
            if self.pending:
                if self.linger_handle:
                    self.linger_handle.cancel()
                    self.linger_handle = None
                texts, self.pending = self.pending, []
                try:
                    res = await self.daemon.server.request("turn/start", {
                        "threadId": self.thread_id,
                        "input": [{"type": "text", "text": t, "text_elements": []} for t in texts]})
                except Exception as e:
                    self.log("turn/start failed: %s" % e)
                    self.last_error = {"message": str(e), "at": now()}
                    await self.finish(3)
                    return
                self.turn_started(res["turn"])
            elif self.linger > 0 and self.linger_handle is None:
                self.status = "idle"
                self.save()
                self.linger_handle = asyncio.get_event_loop().call_later(
                    self.linger, lambda: asyncio.ensure_future(self._linger_expired()))
            elif self.linger <= 0:
                await self.finish({"completed": 0, "failed": 1, "interrupted": 2}.get(self.last_turn_status, 3))

    async def _linger_expired(self):
        if not self.active_turn and not self.pending and self.exit_code is None:
            await self.finish({"completed": 0, "failed": 1, "interrupted": 2}.get(self.last_turn_status, 3))

    async def finish(self, code):
        if self.exit_code is not None:
            return
        self.exit_code = code
        self.status = "exited"
        self.active_turn = None
        self.save()
        write_atomic(os.path.join(self.out, "exit"), "exit %d\n" % code)
        self.events.close()
        self.steer_log.close()
        for w in self.waiters:
            if not w.done():
                w.set_result(self.state())
        self.daemon.task_ended(self)
        if self.thread_id and self.daemon.server.proc:
            with contextlib.suppress(Exception):
                # Unload the thread from the shared app-server so memory does not grow.
                await self.daemon.server.request("thread/unsubscribe", {"threadId": self.thread_id})

    # -- client commands

    async def send(self, text, interrupt):
        if self.exit_code is not None:
            return {"status": "undelivered", "reason": "task has ended; use run --resume"}
        if interrupt:
            await self.interrupt()
        snippet = text[:120].replace("\n", " ")
        if self.active_turn and self.active_turn != self.interrupting and not self.pending:
            turn = self.active_turn
            try:
                await self.daemon.server.request("turn/steer", {
                    "threadId": self.thread_id, "expectedTurnId": turn,
                    "input": [{"type": "text", "text": text, "text_elements": []}]})
                self.log("steered turn %s: %s" % (turn, snippet))
                return {"status": "steered", "turnId": turn}
            except Exception as e:
                # The turn just ended, is a review/compact turn, or the id raced: deliver
                # the message as the next turn instead.
                self.log("steer refused (%s); queued for next turn" % e)
        self.pending.append(text)
        if self.active_turn:
            self.log("queued for next turn: %s" % snippet)
            return {"status": "queued"}
        self.log("starting turn with: %s" % snippet)
        asyncio.ensure_future(self.advance())
        return {"status": "started"}

    async def interrupt(self):
        if not self.active_turn:
            return {"status": "idle"}
        turn = self.interrupting = self.active_turn
        try:
            await self.daemon.server.request("turn/interrupt", {"threadId": self.thread_id, "turnId": turn})
        except Exception as e:
            return {"status": "failed", "reason": str(e)}
        self.log("interrupted turn %s" % turn)
        return {"status": "interrupted", "turnId": turn}

    async def stop(self):
        self.pending = []
        self.linger = 0
        if self.active_turn:
            await self.interrupt()  # turn/completed then ends the task
            return {"status": "stopping"}
        await self.finish(2)
        return {"status": "stopped"}


class Daemon:
    def __init__(self, pool, codex, overrides, idle_exit):
        self.pool = pool
        self.paths = pool_paths(pool)
        self.server = AppServer(self, codex, overrides)
        self.idle_exit = idle_exit
        self.tasks = {}  # out dir -> Task (live and recently ended)
        self.by_thread = {}
        self.idle_handle = None
        self.stopping = asyncio.Event()

    def task_for_thread(self, thread_id):
        return self.by_thread.get(thread_id)

    def live(self):
        return [t for t in self.tasks.values() if t.exit_code is None]

    def on_notification(self, method, params, raw):
        task = self.by_thread.get(params.get("threadId"))
        if task and task.exit_code is None:
            task.on_notification(method, params, raw)

    def on_server_exit(self, code):
        for t in self.live():
            t.last_error = {"message": "app-server exited (code %s)" % code, "at": now()}
            t.log("app-server exited (code %s)" % code)
            asyncio.ensure_future(t.finish(3))

    def task_ended(self, task):
        self.by_thread.pop(task.thread_id, None)
        self.arm_idle()

    def arm_idle(self):
        if self.idle_handle:
            self.idle_handle.cancel()
            self.idle_handle = None
        if not self.live():
            self.idle_handle = asyncio.get_event_loop().call_later(self.idle_exit, self.stopping.set)

    async def handle(self, req):
        cmd = req.get("cmd")
        if cmd == "ping":
            return {"ok": True, "pid": os.getpid(), "version": VERSION}
        if cmd == "run":
            out = req["out"]
            old = self.tasks.get(out)
            if old and old.exit_code is None:
                return {"error": "a live task already uses %s" % out}
            task = Task(self, out, float(req.get("linger") or 0))
            self.tasks[out] = task
            self.arm_idle()
            try:
                await task.start(req["params"], req.get("brief", ""), req.get("resume"))
            except Exception as e:
                task.last_error = {"message": str(e), "at": now()}
                task.log("startup failed: %s" % e)
                await task.finish(3)
                return {"error": "startup failed: %s" % e, "state": task.state()}
            return {"ok": True, "state": task.state()}
        if cmd == "status" and not req.get("out"):
            return {"ok": True, "pid": os.getpid(), "tasks": [t.state() for t in self.tasks.values()]}
        if cmd == "daemon-stop":
            for t in self.live():
                await t.stop()
            asyncio.get_event_loop().call_later(3, self.stopping.set)
            return {"ok": True}
        task = self.tasks.get(req.get("out"))
        if not task:
            return {"error": "no task for %s in pool %s" % (req.get("out"), self.pool)}
        if cmd == "status":
            return {"ok": True, "state": task.state()}
        if cmd == "send":
            res = await task.send(req["text"], req.get("interrupt"))
            return dict(res, ok=res["status"] in DELIVERED)
        if cmd == "interrupt":
            return dict(await task.interrupt(), ok=True)
        if cmd == "stop":
            return dict(await task.stop(), ok=True)
        if cmd == "wait":
            if task.exit_code is not None:
                return {"ok": True, "state": task.state()}
            fut = asyncio.get_event_loop().create_future()
            task.waiters.append(fut)
            return {"ok": True, "state": await fut}
        return {"error": "unknown command %r" % cmd}

    async def client(self, reader, writer):
        try:
            line = await reader.readline()
            req = json.loads(line)
            res = await self.handle(req)
        except Exception as e:
            res = {"error": "%s: %s" % (type(e).__name__, e)}
        with contextlib.suppress(Exception):
            writer.write((json.dumps(res) + "\n").encode())
            await writer.drain()
            writer.close()

    async def main(self):
        with contextlib.suppress(FileNotFoundError):
            os.remove(self.paths["sock"])
        srv = await asyncio.start_unix_server(self.client, path=self.paths["sock"])
        os.chmod(self.paths["sock"], 0o600)
        write_atomic(self.paths["pid"], "%d\n" % os.getpid())
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.stopping.set)
        self.arm_idle()
        await self.stopping.wait()
        srv.close()
        for t in self.live():
            await t.finish(2)
        self.server.stop()
        for p in (self.paths["sock"], self.paths["pid"]):
            with contextlib.suppress(FileNotFoundError):
                os.remove(p)


# ------------------------------------------------------------------------------- client


def call(paths, req, timeout=None):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(paths["sock"])
    s.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
    s.close()
    return json.loads(buf) if buf else {"error": "daemon closed the connection"}


def daemon_alive(paths):
    try:
        return call(paths, {"cmd": "ping"}, timeout=5).get("ok", False)
    except OSError:
        return False


def ensure_daemon(args):
    paths = pool_paths(args.pool)
    if daemon_alive(paths):
        return paths
    with open(paths["lock"], "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if daemon_alive(paths):
            return paths
        cmd = [sys.executable, os.path.abspath(__file__), "daemon", "start", "--foreground",
               "--pool", args.pool, "--idle-exit", str(args.idle_exit)]
        if args.codex:
            cmd += ["--codex", args.codex]
        for c in getattr(args, "daemon_config", None) or []:
            cmd += ["-c", c]
        log = open(paths["log"], "ab")
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        for _ in range(150):
            if daemon_alive(paths):
                return paths
            time.sleep(0.1)
    die("daemon did not start; see %s" % paths["log"])


def print_json(obj):
    sys.stdout.write(json.dumps(obj) + "\n")


def read_text(parts):
    text = " ".join(parts)
    if text in ("", "-"):
        text = sys.stdin.read()
    if not text.strip():
        die("empty message")
    return text


def main():
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--pool", default=os.environ.get("CODEX_STEER_POOL", "default"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = lambda name: sub.add_parser(name, parents=[common])

    r = add("run")
    r.add_argument("--cwd", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--model")
    r.add_argument("--sandbox", default="workspace-write",
                   choices=["read-only", "workspace-write", "danger-full-access"])
    r.add_argument("--approval", default="never")
    r.add_argument("--effort")
    r.add_argument("--resume")
    r.add_argument("--linger", type=float, default=0)
    r.add_argument("-c", "--config", action="append", default=[], help="per-thread config override")
    r.add_argument("--daemon-config", action="append", default=[], help="app-server -c, used only if this run starts the daemon")
    r.add_argument("--codex")
    r.add_argument("--idle-exit", type=float, default=300)
    r.add_argument("--wait", action="store_true", help="block until the task ends; exit with its code")

    s = add("send")
    s.add_argument("out")
    s.add_argument("--interrupt", action="store_true")
    s.add_argument("text", nargs="*")

    for name in ("interrupt", "stop"):
        add(name).add_argument("out")

    w = add("wait")
    w.add_argument("outs", nargs="+")
    w.add_argument("--any", action="store_true", help="return when the first task ends")
    w.add_argument("--timeout", type=float)

    st = add("status")
    st.add_argument("out", nargs="?")

    d = add("daemon")
    d.add_argument("action", choices=["start", "stop", "status"])
    d.add_argument("--foreground", action="store_true", help=argparse.SUPPRESS)
    d.add_argument("--codex")
    d.add_argument("--idle-exit", type=float, default=300)
    d.add_argument("-c", "--config", action="append", default=[])

    args = ap.parse_args()
    paths = pool_paths(args.pool)

    if args.cmd == "daemon":
        if args.action == "start" and args.foreground:
            overrides = [tuple(c.split("=", 1)) for c in args.config]
            asyncio.run(Daemon(args.pool, args.codex, overrides, args.idle_exit).main())
            return
        if args.action == "start":
            args.daemon_config = args.config
            ensure_daemon(args)
            print_json(call(paths, {"cmd": "ping"}))
            return
        if not daemon_alive(paths):
            print_json({"ok": True, "running": False})
            return
        print_json(call(paths, {"cmd": "status" if args.action == "status" else "daemon-stop"}))
        return

    if args.cmd == "run":
        cwd, out = os.path.abspath(args.cwd), os.path.abspath(args.out)
        os.makedirs(out, exist_ok=True)
        brief = "" if sys.stdin.isatty() else sys.stdin.read()
        if not brief.strip() and not args.resume:
            die("empty brief on stdin")
        params = {"cwd": cwd, "sandbox": args.sandbox, "approvalPolicy": args.approval}
        if args.model:
            params["model"] = args.model
        config = dict(parse_override(c) for c in args.config)
        if args.effort:
            config["model_reasoning_effort"] = args.effort
        if config:
            params["config"] = config
        ensure_daemon(args)
        res = call(paths, {"cmd": "run", "out": out, "params": params, "brief": brief,
                           "resume": args.resume, "linger": args.linger})
        if not args.wait or "error" in res:
            print_json(res)
            sys.exit(0 if res.get("ok") else 3)
        res = call(paths, {"cmd": "wait", "out": out})
        print_json(res)
        sys.exit((res.get("state") or {}).get("exit", 3))

    if args.cmd == "status" and not args.out:
        if not daemon_alive(paths):
            print_json({"ok": True, "running": False, "tasks": []})
            return
        print_json(call(paths, {"cmd": "status"}))
        return

    if args.cmd == "wait":
        outs = [os.path.abspath(o) for o in args.outs]
        deadline = time.monotonic() + args.timeout if args.timeout else None
        remaining = set(outs)
        # One waiter thread per task keeps this simple; each blocks on the daemon socket.
        import threading
        results = []
        cond = threading.Condition()

        def waiter(o):
            exit_file = os.path.join(o, "exit")
            try:
                res = call(paths, {"cmd": "wait", "out": o})
            except OSError as e:
                res = {"error": str(e)}
            if "error" in res and os.path.exists(exit_file):
                res = {"ok": True, "state": read_json(os.path.join(o, "state.json"))}
            with cond:
                results.append((o, res))
                cond.notify()

        for o in outs:
            threading.Thread(target=waiter, args=(o,), daemon=True).start()
        code = 0
        with cond:
            while remaining:
                left = None if deadline is None else deadline - time.monotonic()
                if left is not None and left <= 0:
                    print_json({"timeout": True, "running": sorted(remaining)})
                    sys.exit(124)
                cond.wait(left)
                while results:
                    o, res = results.pop()
                    remaining.discard(o)
                    print_json(dict(res, out=o))
                    sys.stdout.flush()
                    st = res.get("state") or {}
                    code = max(code, st.get("exit") if st.get("exit") is not None else 3)
                if args.any and len(remaining) < len(outs):
                    break
        sys.exit(code)

    # Commands that address one task.
    out = os.path.abspath(args.out)
    if not daemon_alive(paths):
        state = read_json(os.path.join(out, "state.json"))
        if args.cmd == "status" and state:
            print_json({"ok": True, "state": state, "daemon": "not running"})
            return
        print_json({"status": "undelivered", "reason": "pool %s is not running" % args.pool})
        sys.exit(1)
    req = {"cmd": args.cmd, "out": out}
    if args.cmd == "send":
        req.update(text=read_text(args.text), interrupt=args.interrupt)
    res = call(paths, req)
    print_json(res)
    if args.cmd == "send":
        sys.exit(0 if res.get("status") in DELIVERED else 1)
    sys.exit(0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
