"""Local, disk-backed processing for Jimmyenglishhome Video Editor."""
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / '.cache'
CACHE.mkdir(exist_ok=True)
os.environ['HF_HOME'] = str(CACHE / 'huggingface')
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'


@dataclass
class Cut:
    start: float
    end: float
    reason: str
    text: str = ''
    selected: bool = False


def merge_cuts(cuts, duration):
    merged = []
    for a, b in sorted((max(0, c.start), min(duration, c.end)) for c in cuts if c.selected):
        if b <= a:
            continue
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


def keep_ranges(cuts, duration):
    result, cursor = [], 0.0
    for a, b in merge_cuts(cuts, duration):
        if a > cursor:
            result.append((cursor, a))
        cursor = b
    if cursor < duration:
        result.append((cursor, duration))
    return result


def suggest(words, segments):
    cuts = []
    fillers = {'um', 'uh', 'erm', 'er', 'hmm'}
    for w in words:
        if re.sub(r'[^a-z]', '', w['word'].lower()) in fillers:
            cuts.append(Cut(w['start'], w['end'], 'Filler (review)', w['word']))
    tokens = [re.sub(r'[^a-z]', '', w['word'].lower()) for w in words]
    phrases = [('you', 'know'), ('i', 'mean'), ('let', 'me', 'start', 'again'), ('scratch', 'that'), ('ignore', 'that')]
    for i in range(len(words)):
        for phrase in phrases:
            if tuple(tokens[i:i+len(phrase)]) == phrase:
                j = i + len(phrase) - 1
                cuts.append(Cut(words[i]['start'], words[j]['end'], 'Possible filler / restart (review)', ' '.join(w['word'] for w in words[i:j+1])))
    recent = []
    for s in segments:
        norm = ' '.join(re.findall(r'[a-z]+', s['text'].lower()))
        if len(norm.split()) >= 3:
            if any(SequenceMatcher(None, norm, old).ratio() >= .9 for old in recent[-5:]):
                cuts.append(Cut(s['start'], s['end'], 'Repeated phrase (review)', s['text']))
            recent.append(norm)
    # Whisper sometimes puts several sentences in one segment. Inspect word-level
    # sentence boundaries too, without duplicating segment-level suggestions.
    sentence, previous = [], []
    for index, word in enumerate(words):
        sentence.append(word)
        if word['word'].rstrip().endswith(('.', '?', '!')) or index == len(words)-1:
            norm = ' '.join(re.findall(r'[a-z]+', ' '.join(w['word'] for w in sentence).lower()))
            if len(norm.split()) >= 3:
                if any(SequenceMatcher(None, norm, old).ratio() >= .9 for old in previous[-5:]):
                    a, b = sentence[0]['start'], sentence[-1]['end']
                    if not any(c.reason.startswith('Repeated') and c.start <= a and c.end >= b for c in cuts):
                        cuts.append(Cut(a, b, 'Repeated sentence (review)', ' '.join(w['word'] for w in sentence)))
                previous.append(norm)
            sentence = []
    return cuts


def timestamp(seconds):
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def subtitles(words, ranges, speed, frame_rate=None):
    cues, group, offset = [], [], 0.0
    def flush():
        if group:
            cues.append((group[0][0], group[-1][1], ' '.join(x[2].strip() for x in group)))
            group.clear()
    for a, b in ranges:
        for w in words:
            # Omit words intersected by a cut instead of displaying cut speech.
            if w['start'] >= a - .001 and w['end'] <= b + .001:
                start = (offset + w['start'] - a) / speed
                end = (offset + w['end'] - a) / speed
                if group and (start - group[0][0] > 3.5 or len(group) >= 9):
                    flush()
                group.append((start, max(start + .03, end), w['word']))
                if w['word'].rstrip().endswith(('.', '?', '!')):
                    flush()
        flush()
        offset += (math.ceil((b-a) / speed * frame_rate) / frame_rate * speed
                   if frame_rate else b-a)
    return '\n\n'.join(f'{i}\n{timestamp(a)} --> {timestamp(b)}\n{text}' for i, (a, b, text) in enumerate(cues, 1)) + '\n'


class Processor:
    def __init__(self, progress=lambda p, text: None):
        import imageio_ffmpeg
        self.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        self.progress = progress
        self.cancel = threading.Event()

    def run(self, args, duration=0, base=0, span=0):
        if self.cancel.is_set():
            raise RuntimeError('Cancelled')
        with tempfile.TemporaryFile(mode='w+b', dir=CACHE) as errors:
            proc = subprocess.Popen([self.ffmpeg, '-hide_banner', '-nostdin', '-y', *args,
                                     '-progress', 'pipe:1', '-nostats'], stdout=subprocess.PIPE,
                                    stderr=errors, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            def stop():
                while proc.poll() is None:
                    if self.cancel.wait(.2):
                        if proc.poll() is None:
                            proc.terminate()
                        return
            watcher = threading.Thread(target=stop, daemon=True)
            watcher.start()
            for raw in proc.stdout:
                line = raw.decode(errors='replace').strip()
                if line.startswith('out_time_us=') and duration:
                    try:
                        self.progress(min(base + span, base + span * int(line.split('=')[1]) / 1e6 / duration), 'Processing video…')
                    except ValueError:
                        pass
            proc.stdout.close()
            proc.wait()
            watcher.join(timeout=.3)
            errors.seek(0)
            log = errors.read().decode(errors='replace')
        if self.cancel.is_set():
            raise RuntimeError('Cancelled')
        if proc.returncode:
            raise RuntimeError(log[-5000:])
        return log

    def probe(self, source):
        p = subprocess.run([self.ffmpeg, '-hide_banner', '-i', str(source)], capture_output=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        log = p.stderr.decode(errors='replace')
        match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', log)
        if not match or 'Video:' not in log:
            raise RuntimeError('Cannot read this video. Choose a normal video file with a known duration.')
        h, m, s = map(float, match.groups())
        return {'duration': h * 3600 + m * 60 + s, 'audio': 'Audio:' in log}

    def analyze(self, source, model_name, speech=True):
        info = self.probe(source)
        result = dict(info, words=[], segments=[], cuts=[])
        if not info['audio']:
            return result
        self.progress(2, 'Detecting silent pauses…')
        log = self.run(['-i', str(source), '-vn', '-af', 'silencedetect=noise=-35dB:d=2', '-f', 'null', '-'], info['duration'], 2, 18)
        start = None
        for kind, value in re.findall(r'silence_(start|end):\s*([\d.]+)', log):
            if kind == 'start':
                start = float(value)
            elif start is not None:
                end = float(value)
                if end - start > 2:
                    result['cuts'].append(Cut(start + .15, end - .15, 'Silence > 2 seconds', selected=True))
                start = None
        if start is not None and info['duration'] - start > 2:
            result['cuts'].append(Cut(start + .15, info['duration'], 'Trailing silence', selected=True))
        if speech:
            self.progress(22, 'Loading Whisper model (first use downloads model files)…')
            with tempfile.TemporaryDirectory(dir=CACHE) as folder:
                wav = Path(folder) / 'speech.wav'
                self.run(['-i', str(source), '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(wav)])
                recognized = self.recognize(wav, Path(folder) / 'recognized.json', model_name, info['duration'])
                result.update(recognized)
            result['cuts'].extend(suggest(result['words'], result['segments']))
        self.progress(100, 'Analysis ready. Review suggested cuts and transcript.')
        return result

    def recognize(self, audio, output, model_name, duration):
        with tempfile.TemporaryFile(mode='w+b', dir=CACHE) as errors:
            proc = subprocess.Popen([sys.executable, '-u', str(ROOT / 'speech_worker.py'), model_name, str(audio), str(output)], stdout=subprocess.PIPE, stderr=errors, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            def stop():
                while proc.poll() is None:
                    if self.cancel.wait(.2):
                        if proc.poll() is None:
                            proc.terminate()
                        return
            watcher = threading.Thread(target=stop, daemon=True)
            watcher.start()
            for raw in proc.stdout:
                try:
                    end = json.loads(raw)['end']
                    self.progress(25 + 70 * end / duration, 'Recognizing English speech…')
                except (ValueError, KeyError):
                    pass
            proc.stdout.close()
            proc.wait()
            watcher.join(timeout=.3)
            errors.seek(0)
            log = errors.read().decode(errors='replace')
        if self.cancel.is_set():
            raise RuntimeError('Cancelled')
        if proc.returncode:
            raise RuntimeError(f'Whisper stopped (exit code {proc.returncode}). Check the model download and installed speech dependencies.\n{log[-3500:]}')
        return json.loads(output.read_text(encoding='utf-8'))

    def brightness(self, source):
        self.progress(1, 'Measuring image brightness…')
        log = self.run(['-i', str(source), '-t', '60', '-vf', 'fps=1/5,scale=160:-2,signalstats,metadata=print:key=lavfi.signalstats.YAVG', '-an', '-f', 'null', '-'])
        values = [float(v) for v in re.findall(r'lavfi.signalstats.YAVG=([\d.]+)', log)]
        avg = sum(values) / len(values) if values else 112
        return max(-.08, min(.10, (112 - avg) / 255))

    def render(self, source, output, analysis, options, preview=False):
        source, output = Path(source).resolve(), Path(output).resolve()
        if source == output:
            raise ValueError('Choose a new output file. The original video cannot be overwritten.')
        partial = output.with_name(output.stem + '.partial.mp4')
        if partial == source:
            raise ValueError('The temporary export filename conflicts with your original. Choose a different output name.')
        if partial.exists():
            raise ValueError(f'Temporary export file already exists: {partial}. Move it or choose another output name.')
        cuts = [c for c in analysis['cuts'] if c.selected and (options['silence'] or not c.reason.startswith(('Silence', 'Trailing')))]
        ranges = keep_ranges(cuts, analysis['duration'])
        if preview:
            remaining, short = 30., []
            for a, b in ranges:
                short.append((a, min(b, a + remaining)))
                remaining -= short[-1][1] - a
                if remaining <= 0:
                    break
            ranges = short
        if not ranges or sum(b-a for a,b in ranges) < .1:
            raise ValueError('The selected cuts remove the entire video.')
        speed = 1.2 if options['speed'] else 1.
        total = sum(math.ceil((b-a)/speed*30)/30 for a,b in ranges)
        correction = self.brightness(source) if options['brightness'] else 0
        with tempfile.TemporaryDirectory(dir=CACHE) as folder:
            work = Path(folder)
            watermark = work / 'watermark.txt'
            watermark.write_text(options['watermark_text'], encoding='utf-8')
            filters = []
            if options['brightness']:
                filters += [f'eq=brightness={correction:.5f}:contrast=1.025:saturation=1.025', 'unsharp=5:5:0.25:5:5:0']
            if options['smooth']:
                filters += ['hqdn3d=1.0:0.8:1.5:1.2']
            width, height = (1280, 720) if preview else (1920, 1080)
            filters += [f'scale={width}:{height}:force_original_aspect_ratio=decrease', f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2', 'setsar=1', f'setpts=(PTS-STARTPTS)/{speed}', 'fps=30']
            if options['watermark'] and options['watermark_text'].strip():
                # Use a relative text file to avoid escaping user text or Windows paths in filters.
                filters += [f"drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':textfile=watermark.txt:expansion=none:fontsize={options['watermark_size']}:fontcolor=white@0.8:shadowcolor=black@0.7:shadowx=2:shadowy=2:x=w-tw-30:y=h-th-30"]
            elapsed = 0
            for i, (a, b) in enumerate(ranges):
                segment_duration = math.ceil((b-a)/speed*30)/30
                segment_filters = filters + [f'tpad=stop_mode=clone:stop_duration=0.1,trim=duration={segment_duration}']
                args = ['-ss', str(a), '-t', str(b-a), '-i', str(source), '-map', '0:v:0', '-vf', ','.join(segment_filters), '-c:v', 'libx264', '-preset', 'fast', '-crf', '21', '-pix_fmt', 'yuv420p']
                if analysis['audio']:
                    args += ['-map', '0:a:0', '-af', f'asetpts=PTS-STARTPTS,atempo={speed},aresample=48000,apad,atrim=duration={segment_duration}', '-c:a', 'pcm_s16le']
                else:
                    args += ['-an']
                args += [str(work / f'part{i:06}.mkv')]
                # drawtext's relative file resolves against the child process working directory.
                self.run_in_work(args, work, segment_duration, 5+elapsed/total*80, segment_duration/total*80)
                elapsed += segment_duration
            (work / 'parts.txt').write_text(''.join(f"file 'part{i:06}.mkv'\n" for i in range(len(ranges))), encoding='utf-8')
            srt = subtitles(analysis['words'], ranges, speed, frame_rate=30) if options['subtitles'] else ''
            if srt.strip():
                (work / 'captions.srt').write_text(srt, encoding='utf-8')
            args = ['-f', 'concat', '-safe', '0', '-i', str(work / 'parts.txt')]
            if srt.strip():
                args += ['-i', str(work / 'captions.srt')]
            args += ['-map', '0:v:0', '-map', '0:a?', '-c:v', 'copy']
            if analysis['audio']:
                if options['noise']:
                    args += ['-af', 'highpass=f=70,afftdn=nf=-25,dynaudnorm=f=250:g=15', '-c:a', 'aac', '-b:a', '192k']
                else:
                    args += ['-c:a', 'aac', '-b:a', '192k']
            if srt.strip():
                args += ['-map', '1:0', '-c:s', 'mov_text', '-metadata:s:s:0', 'language=eng', '-disposition:s:0', 'default']
            try:
                self.run(args + ['-movflags', '+faststart', str(partial)], total, 85, 14)
                if self.cancel.is_set():
                    raise RuntimeError('Cancelled')
                os.replace(partial, output)
            finally:
                partial.unlink(missing_ok=True)
            if srt.strip():
                output.with_suffix('.srt').write_text(srt, encoding='utf-8')
        self.progress(100, 'Video ready')
        return output

    def run_in_work(self, args, work, duration, base, span):
        # Absolute textfile path is escaped for FFmpeg, without changing global cwd.
        escaped = str(work / 'watermark.txt').replace('\\', '/').replace(':', '\\:')
        args = [v.replace('textfile=watermark.txt', f"textfile='{escaped}'") for v in args]
        return self.run(args, duration, base, span)
