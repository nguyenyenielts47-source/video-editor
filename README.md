# Jimmyenglishhome Video Editor

A local Python desktop application for English teaching videos on Windows 11. Uses Tkinter, FFmpeg, and the Whisper speech recognition model through faster-whisper. No API keys or cloud processing.

## Launch on this computer

Double-click **Launch.bat** in this folder. Keep the folder and its hidden `.tools` and `.cache` subfolders together. Python and FFmpeg dependencies are installed locally during setup; no system FFmpeg installation is needed.

## Use the editor

1. **Select video**. **Play original** opens the original in your default Windows video player.
2. Choose editing features. Start with `base.en` for English recognition; `small.en` may improve recognition but uses more CPU and memory. Disable Whisper analysis and subtitles for a quick edit without speech recognition.
3. Click **Analyze video**. On first use, approve the model download. The first download needs internet access; your video and audio are never uploaded. Wait for recognition to finish.
4. Review **Suggested cuts**. Double-click a row to switch between `Keep` and `YES`. Long silent pauses (below -35 dB for more than two seconds) start selected, with a small breathing margin. Speech cuts start unchecked. Repeated lesson sentences may be intentional. Turning off silence removal keeps all detected silent pauses, even if their rows show YES.
5. Review **Transcript / subtitle corrections**. Double-click words to correct spelling and punctuation. Select words and click **Suggest cut for selected words** to mark unnecessary speech, then enable that cut in Suggested cuts. **Add a cut by time** accepts original-video seconds.
6. Choose watermark text and font size. The watermark appears in the bottom-right corner.
7. Click **Preview edits**. It renders the first 30 seconds of retained source footage at 720p and opens the result in your default video player. Export uses the same edit choices at 1080p. Enable subtitles in the player's subtitle menu if necessary. Preview length is shorter with 1.2× speed.
8. Click **Export 1080p MP4**, choose a new filename, and wait for completion. The MP4 contains H.264 video, AAC audio when available, and a default English selectable subtitle track when enabled. An SRT file is saved alongside it. Original files are never modified.

You can cancel processing. FFmpeg stops promptly; Whisper cancellation waits for the current recognition segment or download. The GUI remains responsive while processing. Close the player before regenerating a preview if Windows reports that the preview file is in use.

## Features and practical limits

- Brightness uses sampled luminance from the first minute to choose a restrained correction; light contrast and sharpening improve presentation. It is not a restoration or upscaling AI.
- Smoothing uses a mild whole-frame spatial/temporal denoiser to soften noise and skin texture without strong beauty effects. It is **not face-aware retouching**. Leave it off if small text or facial details become too soft.
- `atempo=1.2` changes speed while preserving voice pitch. Noise reduction, a speech high-pass filter, and dynamic normalization reduce steady noise and even speech volume. They cannot reliably remove other people speaking or severe distortion.
- Whisper recognizes English locally with word timestamps. Accuracy and timing depend on microphone quality, accent, and model size; always proofread teaching material. Cut and speed changes are reflected in subtitle timestamps.
- Speech suggestions are conservative transcript heuristics for repeated segments, filler words/phrases, and restart phrases. They are **not a semantic judge of unnecessary teaching content**. Whisper can omit fillers or combine sentences, so review and manual cuts remain necessary.
- Subtitles are selectable, not permanently burned into the picture. Use a compatible player such as Windows Media Player or VLC and enable subtitles. Some upload services require uploading the SRT separately.
- Export is landscape 1920×1080, 30 fps, with letterboxing for other aspect ratios. HDR/color-managed mastering and multiple audio tracks are outside this version's scope. The first video/audio streams are used.
- Large videos are read from disk and rendered in sequential retained sections, not loaded into memory. Whisper still needs model RAM. Temporary H.264 video and uncompressed audio require substantial free space in this project folder; allow several GB for long lessons. Temporary processing folders are removed when jobs finish or fail normally. A forced process kill may leave temporary folders in `.cache`.
- Progress reflects FFmpeg output time and recognized speech position. Model download/loading can stay at one percentage for a while. Model loading is CPU-only for straightforward installation.
- **Save review** writes a JSON report of the transcript and cuts for reference. This version does not reopen saved reviews.

## Setup on another Windows 11 computer

Install 64-bit Python 3.12 or newer from [python.org](https://www.python.org/downloads/windows/) with pip and Tcl/Tk selected. Installing Python may require your Windows approval. In PowerShell opened in this project folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\Setup.ps1
```

This creates a project virtual environment if the bundled project Python is absent, installs `requirements.txt`, and obtains FFmpeg through imageio-ffmpeg. Dependency and model downloads need internet access. After dependencies and a chosen model are cached, editing runs offline. Models and pip cache remain under `.cache`; exported videos are saved where you choose.

To run directly in this configured project:

```powershell
.\.tools\python\python.exe app.py
```

## Tests and troubleshooting

```powershell
.\.tools\python\python.exe -m unittest discover -s tests -v
```

Tests generate small sample videos inside `.cache/test-output`, check actual FFmpeg export/decode, watermark escaping, 1080p dimensions, subtitle muxing, silence cuts, silent input, original preservation, cancellation, and timeline calculations. They do not need a Whisper model. See `TESTING.md` for checks actually performed in this environment.

If an operation fails, read the dialog and `.cache/last-error.log`. For a model download failure, retry with internet access; for memory trouble, choose `tiny.en` or `base.en`. If subtitles are missing, enable Whisper and subtitles, analyze again, and check that the transcript contains words. Keep sufficient free disk space on both the project and export drives.

Implementation references: [FFmpeg filter documentation](https://ffmpeg.org/ffmpeg-filters.html) and [faster-whisper documentation](https://github.com/SYSTRAN/faster-whisper).
