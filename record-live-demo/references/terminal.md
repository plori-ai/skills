# Terminal demos

Use a real pseudo-terminal for interactive programs. Capturing a replay of stdout after the command finishes loses input timing, cursor movement, ANSI state, prompts, approvals, and spinners.

## Preferred setup

1. Spawn the requested shell or CLI through a PTY such as `node-pty`.
2. Mirror the PTY byte stream into xterm.js in a dedicated 1280x720 page.
3. Send keystrokes through the PTY. Type the command, press Enter, wait for the program, then type the task.
4. Record the xterm page with Playwright video, a browser screencast, or a stable OS recorder.
5. Wait for the CLI's real terminal condition, then hold the final result for several seconds.

Use a fixed terminal size and a readable font. Preserve ANSI output. Hide shell history, environment variables, tokens, and unrelated filesystem paths before capture.

For an interactive coding agent, show the product's own TUI and tool-call status. Do not replace it with a custom animation that merely resembles the CLI.

## Failure boundaries

- A command echo is not proof that the command ran. Keep the exit or success output visible.
- If the program asks for approval or login, let the user take over when required. Keep the recorder running only if the prompt does not expose secrets.
- Stop on success, a clear CLI error, or the agreed timeout. Save the raw recording before attempting another take.
