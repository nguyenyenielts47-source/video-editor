"""Isolated Whisper process so a native-library failure cannot close the editor."""
import json
import os
import sys
from pathlib import Path
from engine import CACHE


def main():
    from faster_whisper import WhisperModel
    model_name, audio, output = sys.argv[1:4]
    kwargs = dict(device='cpu', compute_type='int8', cpu_threads=min(4, os.cpu_count() or 2), download_root=str(CACHE / 'models'))
    from huggingface_hub.errors import LocalEntryNotFoundError
    try:
        model = WhisperModel(model_name, local_files_only=True, **kwargs)
    except (LocalEntryNotFoundError, FileNotFoundError):
        model = WhisperModel(model_name, **kwargs)
    segments, _ = model.transcribe(audio, language='en', word_timestamps=True, vad_filter=True, beam_size=5)
    result = {'words': [], 'segments': []}
    for segment in segments:
        result['segments'].append({'start': segment.start, 'end': segment.end, 'text': segment.text.strip()})
        for word in segment.words or []:
            result['words'].append({'start': word.start, 'end': word.end, 'word': word.word.strip()})
        print(json.dumps({'end': segment.end}), flush=True)
    Path(output).write_text(json.dumps(result), encoding='utf-8')


if __name__ == '__main__':
    main()
