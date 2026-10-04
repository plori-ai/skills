# Browser demos

Use the browser surface the user requested. Reuse its signed-in session when allowed, and keep the page interaction inside the supported browser-control tool rather than launching a separate automation profile.

## Capture priority

1. Native tab video or browser screencast.
2. A stable OS/window recorder cropped to the browser.
3. Browser-native viewport frames captured during the live run.

The third option is a real recording of the running page, but its temporal resolution is the capture rate. Do not describe a 5 fps source as native 30 fps motion merely because the delivery file duplicates frames at 30 fps.

## Viewport-frame fallback

When direct tab video is unavailable, capture `tab.screenshot({})` at a fixed rate while the real browser actions run. The capture loop and the actions must live in the same long-running browser execution. Unawaited background capture may be discarded when a tool call returns.

Use this shape:

```js
let stop = false;
const capture = (async () => {
  while (!stop) {
    const started = Date.now();
    const bytes = await tab.screenshot({});
    await fs.writeFile(nextFrameName(), bytes);
    const remaining = 200 - (Date.now() - started); // target 5 fps
    if (remaining > 0) await new Promise(r => setTimeout(r, remaining));
  }
})();

await performRealBrowserActions();
await waitForVisibleSuccess();
await new Promise(r => setTimeout(r, 8000));
stop = true;
await capture;
```

Save frame timestamps when exact real-time reconstruction matters. Detect the returned image format with `file`; some browser APIs return JPEG bytes even when a caller gives the file a `.png` suffix.

## Interaction details

- Keep the composer and live result area visible.
- Verify whether Enter submits. For long prompts, use one paragraph or the page's supported multiline shortcut.
- When character-by-character typing has a short action deadline, send small chunks. Do not let a timeout leave a partial prompt unnoticed.
- Define success from visible page state, such as a run ID, output path, updated range, or succeeded status. Keep a final screenshot as evidence.
- Prefer a dedicated 16:9 tab. A narrow side panel produces a vertical recording even if the desktop is landscape.
