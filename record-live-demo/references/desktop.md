# Desktop and native-app demos

Use a window or region recorder for native apps and cross-app flows. Crop tightly enough to protect unrelated content while leaving menus, dialogs, and the final result understandable.

## Reliable recording

- Prefer OBS, QuickTime, ScreenCaptureKit, or another recorder with explicit start and stop semantics.
- When using ffmpeg, capture to MKV or fragmented MP4 so an interrupted process is less likely to lose the whole take. Remux or re-encode to delivery MP4 afterward.
- Confirm screen-recording permission and make a short test file before the final action.
- Verify that the output file exists and grows before triggering an external write.

On macOS, `screencapture -R` uses logical display points while ordinary screenshots may report Retina pixels. Test the crop instead of assuming both coordinate systems match.

Do not stop `screencapture -v` with `Ctrl+C` unless a test proves the current OS version finalizes the file. It may cancel an unsealed recording. Prefer the recorder's stop control or an agreed fixed duration.

Silence notifications and hide other apps. If the system recorder cannot isolate the target window reliably, use an application-native or browser-native capture instead of recording the whole desktop.
