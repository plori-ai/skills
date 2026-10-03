---
name: record-live-demo
description: Record genuine, continuous product demonstrations of terminal, browser, or desktop workflows, then verify and derive delivery-ready MP4s. Use for live demos, screen recordings, product walkthroughs, CLI sessions, browser workflows, and trim or speed edits. Do not use for synthetic motion graphics, slide videos, or image-storyboard videos.
---

# Record Live Demo

Produce a real demonstration of the requested product behavior. The visible input, waiting, tool activity, and final result must come from the live system. Do not recreate the run with staged screenshots or simulated output.

## Choose the capture mode

- For an interactive CLI or coding agent, read [references/terminal.md](references/terminal.md).
- For a website or browser-based product, read [references/browser.md](references/browser.md).
- For a native app, full desktop, or cross-app flow, read [references/desktop.md](references/desktop.md).

Use the narrowest capture surface that shows the whole task. A dedicated 16:9 terminal or browser viewport is preferable to a desktop crop containing unrelated windows.

## Protect authenticity and scope

- Start the real program and perform the real interaction while capture is active.
- Preserve the user's chosen product, browser, account, prompt, and destination.
- Treat writes, purchases, messages, workflow activation, and other external effects as the underlying action, not as permission granted by recording. Confirm or rely on existing authorization at action time.
- Before a write, prove that capture is producing frames or that the recording file is growing. A successful product action with a failed recorder is not a successful take.
- Use test accounts, analytics-suppression headers, and append-only demo data when the environment provides them. Never expose tokens, credentials, notifications, or unrelated customer data.
- If a recorded write succeeds but capture fails, report the side effect before retrying. Do not repeat a mutation blindly.

## Record the take

1. Define the visible starting state, exact prompt or actions, success evidence, permitted side effects, and timeout.
2. Dry-run controls and selectors without performing the final external write. Confirm the intended viewport and recorder output.
3. Start capture. Verify its health before entering the prompt or initiating the real action.
4. Record input at a readable pace. Let the system work in real time. Do not skip waiting merely to make the take shorter.
5. Stop when the requested result is visibly complete. Hold the success state for 5 to 8 seconds.
6. Stop the recorder gracefully. Keep the raw, full-speed take.
7. Encode and verify the delivery copy. Create trims, speed changes, captions, or crops as separate derived files.

Stop on a visible success, a clear product error, a user decision point, or the agreed timeout. Do not turn an unsuccessful run into a success through editing.

## Delivery contract

Default to H.264 MP4, `yuv420p`, fast start, and a 16:9 frame at 1280x720 or 1920x1080. Do not add captions when the destination generates them automatically.

Deliver:

- the untouched original take;
- any requested derived version under a different filename;
- duration, resolution, and whether audio is present;
- the visible success evidence and any external data created during retries.

Verify the first, middle, and final sections rather than checking only that the file opens. The final frame should show the result, not a spinner or blank page.

## Helpers

- `scripts/finalize_video.sh INPUT OUTPUT` converts a raw recording to a compatible MP4.
- `scripts/encode_frames.sh FRAMES_DIR CAPTURE_FPS OUTPUT` encodes `frame-000000.jpg` or `.png` sequences.
- `scripts/trim_and_speed.py INPUT KEEP_SECONDS SPEED OUTPUT` keeps the beginning of a take and changes playback speed without overwriting the source.
- `scripts/inspect_video.sh INPUT [CONTACT_SHEET]` reports media properties and optionally creates a nine-frame contact sheet. Its last tile comes from about eight-ninths of the way through, not the final frame, so check the final frame separately.

Run helpers from the skill directory or by absolute path. Keep intermediate frames outside the user's repository unless they explicitly want them committed.
