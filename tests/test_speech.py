import json
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from faster_whisper.audio import decode_audio
import speech_worker
from engine import CACHE, Cut, Processor, keep_ranges, subtitles


class SpeechTests(unittest.TestCase):
    def test_real_audio_decoder(self):
        # This exact call raised metadata_errors with PyAV 19.0.2.
        with tempfile.TemporaryDirectory(dir=CACHE) as folder:
            path = Path(folder) / 'English audio.wav'
            samples = (np.sin(np.arange(16000) * .1) * 1000).astype('<i2')
            with wave.open(str(path), 'wb') as wav:
                wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                wav.writeframes(samples.tobytes())
            audio = decode_audio(str(path))
            self.assertEqual(audio.shape, (16000,))
            self.assertEqual(audio.dtype, np.float32)
            self.assertGreater(float(np.max(np.abs(audio))), .01)

    def test_worker_english_word_timestamps_and_json(self):
        words = [SimpleNamespace(start=.1, end=.4, word=' Hello'),
                 SimpleNamespace(start=.4, end=.8, word=' world.')]
        segment = SimpleNamespace(start=.1, end=.8, text=' Hello world.', words=words)
        with tempfile.TemporaryDirectory(dir=CACHE) as folder:
            output = Path(folder) / 'recognized.json'
            with patch('faster_whisper.WhisperModel') as model, patch(
                'sys.argv', ['speech_worker.py', 'tiny.en', 'speech.wav', str(output)]
            ):
                model.return_value.transcribe.return_value = (iter([segment]), None)
                speech_worker.main()
                options = model.return_value.transcribe.call_args.kwargs
                self.assertEqual(options['language'], 'en')
                self.assertTrue(options['word_timestamps'])
                self.assertTrue(options['vad_filter'])
            result = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(result['words'][0]['word'], 'Hello')
            self.assertIn('Hello world.', subtitles(result['words'], [(0, 1)], 1))

    def test_subtitles_after_cut_speed_and_correction(self):
        words = [dict(start=0, end=.6, word='Hello!'),
                 dict(start=1, end=1.2, word='removed'),
                 dict(start=2, end=2.6, word='Corrected café.')]
        ranges = keep_ranges([Cut(.8, 2, 'Manual', selected=True)], 3)
        srt = subtitles(words, ranges, 1.2, frame_rate=30)
        self.assertIn('00:00:00,000 --> 00:00:00,500', srt)
        self.assertIn('00:00:00,700 --> 00:00:01,200', srt)
        self.assertIn('Corrected café.', srt)
        self.assertNotIn('removed', srt)

    def test_real_export_and_english_subtitle_track(self):
        import av
        with tempfile.TemporaryDirectory(dir=CACHE) as folder:
            source, output = [Path(folder) / name for name in ('source.mp4', 'edited.mp4')]
            processor = Processor()
            processor.run(['-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=30:d=1',
                           '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
                           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)])
            original = source.read_bytes()
            analysis = processor.analyze(source, 'tiny.en', speech=False)
            analysis['words'] = [dict(start=.1, end=.5, word='Hello world.')]
            options = dict(brightness=True, smooth=True, speed=True, noise=True,
                           silence=True, subtitles=True, watermark=False,
                           watermark_text='Jimmyenglishhome', watermark_size=32)
            processor.render(source, output, analysis, options)
            self.assertEqual(source.read_bytes(), original)
            self.assertIn('Hello world.', output.with_suffix('.srt').read_text(encoding='utf-8'))
            with av.open(str(output)) as container:
                self.assertEqual((container.streams.video[0].width, container.streams.video[0].height), (1920, 1080))
                self.assertEqual(len(container.streams.audio), 1)
                track = container.streams.subtitles[0]
                self.assertEqual(track.metadata['language'], 'eng')
                self.assertEqual(track.codec_context.name, 'mov_text')
                self.assertTrue(list(container.decode(video=0)))

    def test_cancellation(self):
        processor = Processor()
        processor.cancel.set()
        with self.assertRaisesRegex(RuntimeError, 'Cancelled'):
            processor.run([])


if __name__ == '__main__':
    unittest.main()
