# Whisper compatibility validation

Validated on Linux, Python 3.12.14. This was not a Windows desktop UI test.

- Reproduced the reported TypeError using faster-whisper 1.2.1, PyAV 19.0.2,
  and a generated mono 16 kHz WAV through faster_whisper.audio.decode_audio.
- Installed PyAV 16.0.1 and ran the same real decoder successfully.
- All 5 regression tests passed (`python -m unittest discover -s tests -v`).
  These cover real decoding, the worker's English and word timestamp options
  with mocked model output, corrected UTF-8 SRT timing after cuts and speed
  changes (including frame rounding), real FFmpeg 1080p export/decode with audio
  processing and smoothing, English mov_text track metadata and SRT output,
  original file preservation, and cancellation before processing.
- Dependency check passed using `uv pip check` in the supplied environment.
- Downloaded the official av 16.0.1 CPython 3.12 Windows x64 wheel successfully,
  confirming that this version needs no local FFmpeg compilation on that target.
- Real speech recognition was attempted using upstream faster-whisper's jfk.flac
  sample and Systran/faster-whisper-tiny.en. Model weights could not be downloaded:
  the model download endpoint returned HTTP 403. Therefore real model inference
  and recognition accuracy were not verified here. Worker behavior is covered by
  a mocked model test; audio decoding and video export use real libraries.
- Windows PowerShell setup, GUI interaction, the Windows watermark font, and
  playback in Windows players still need a Windows smoke test. The application
  source and Launch.bat are unchanged, preserving existing editing features.

## Windows smoke test

Run Setup.ps1, launch Launch.bat, choose a short English video and tiny.en or
base.en, and allow the model download. Analyze with Whisper enabled. Confirm
words appear in the transcript; correct a word; select a cut; enable speed and
subtitles; preview and export. Enable English subtitles in your player and check
the matching SRT. Try your usual watermark and editing options as well.
