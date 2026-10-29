"""Beginner-friendly Windows desktop editor. Run with Python 3.12+."""
import json
import os
import queue
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from dataclasses import asdict
from pathlib import Path

from engine import Processor, Cut, ROOT, CACHE


class Editor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Jimmyenglishhome Video Editor')
        self.geometry('1120x820')
        self.minsize(940, 700)
        self.source = None
        self.analysis = None
        self.processor = None
        self.busy = False
        self.events = queue.Queue()
        self.buttons = []
        self.preview_path = None
        self.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TButton', padding=6)
        style.configure('Title.TLabel', font=('Segoe UI', 18, 'bold'))
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Jimmyenglishhome Video Editor', style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer, text='1. Select a video   →   2. Analyze and review   →   3. Preview   →   4. Export 1080p').pack(anchor='w', pady=(4, 12))
        row = ttk.Frame(outer)
        row.pack(fill='x')
        self.button(row, 'Select video…', self.select).pack(side='left')
        self.button(row, 'Play original', self.play_original).pack(side='left', padx=6)
        self.file_label = ttk.Label(row, text='No video selected', wraplength=720)
        self.file_label.pack(side='left', padx=8)

        settings = ttk.LabelFrame(outer, text='Editing features — turn each feature on or off', padding=10)
        settings.pack(fill='x', pady=12)
        self.flags = {}
        features = [('brightness', 'Auto brightness + gentle sharpening', True),
                    ('smooth', 'Gentle smoothing (whole image)', False),
                    ('speed', 'Speed 1.2× — preserve voice pitch', True),
                    ('noise', 'Reduce noise + clarify speech', True),
                    ('silence', 'Remove selected silent pauses > 2 s', True),
                    ('subtitles', 'English subtitles (selectable track + SRT)', True),
                    ('watermark', 'Bottom-right watermark', True),
                    ('speech', 'Whisper speech analysis / cut suggestions', True)]
        for i, (key, label, default) in enumerate(features):
            self.flags[key] = tk.BooleanVar(value=default)
            ttk.Checkbutton(settings, text=label, variable=self.flags[key]).grid(row=i//2, column=i%2, sticky='w', padx=(0, 24), pady=2)
        ttk.Label(settings, text='Watermark text:').grid(row=4, column=0, sticky='w', pady=(8, 0))
        self.watermark = tk.StringVar(value='Jimmyenglishhome')
        ttk.Entry(settings, textvariable=self.watermark, width=36).grid(row=5, column=0, sticky='w')
        custom = ttk.Frame(settings)
        custom.grid(row=5, column=1, sticky='w')
        ttk.Label(custom, text='Size:').pack(side='left')
        self.fontsize = tk.IntVar(value=32)
        ttk.Spinbox(custom, from_=16, to=72, textvariable=self.fontsize, width=5).pack(side='left', padx=5)
        ttk.Label(custom, text='Whisper model:').pack(side='left', padx=(12, 4))
        self.model = tk.StringVar(value='base.en')
        ttk.Combobox(custom, textvariable=self.model, state='readonly', values=['tiny.en', 'base.en', 'small.en', 'medium.en'], width=12).pack(side='left')
        ttk.Label(settings, text='Smoothing is a subtle image filter, not face-aware AI. Larger Whisper models are slower but may improve accuracy.').grid(row=6, column=0, columnspan=2, sticky='w', pady=(8, 0))

        actions = ttk.Frame(outer)
        actions.pack(fill='x', pady=(0, 8))
        self.button(actions, 'Analyze video', self.analyze).pack(side='left')
        self.button(actions, 'Preview edits (first 30 s)', lambda: self.render(True)).pack(side='left', padx=6)
        self.button(actions, 'Export 1080p MP4…', lambda: self.render(False)).pack(side='left')
        self.button(actions, 'Save review…', self.save_review).pack(side='left', padx=6)
        self.cancel_button = ttk.Button(actions, text='Cancel processing', command=self.cancel, state='disabled')
        self.cancel_button.pack(side='right')

        notebook = ttk.Notebook(outer)
        notebook.pack(fill='both', expand=True)
        review = ttk.Frame(notebook, padding=8)
        transcript = ttk.Frame(notebook, padding=8)
        notebook.add(review, text='Suggested cuts')
        notebook.add(transcript, text='Transcript / subtitle corrections')
        ttk.Label(review, text='Double-click a row to keep/cut it. Speech suggestions require your review; teaching repetitions may be intentional.').pack(anchor='w')
        self.cut_tree = self.tree(review, [('use', 'Cut?', 55), ('start', 'Start (s)', 80), ('end', 'End (s)', 80), ('reason', 'Reason', 190), ('text', 'Speech / notes', 550)])
        self.cut_tree.bind('<Double-1>', self.toggle_cut)
        review_buttons = ttk.Frame(review)
        review_buttons.pack(fill='x', pady=5)
        self.button(review_buttons, 'Keep all speech suggestions', self.clear_speech).pack(side='left')
        self.button(review_buttons, 'Add a cut by time…', self.manual_cut).pack(side='left', padx=6)
        self.button(review_buttons, 'Delete selected suggestion', self.delete_cut).pack(side='left')
        ttk.Label(transcript, text='Double-click a word to correct its spelling. Select words, then suggest a cut for unnecessary speech.').pack(anchor='w')
        self.words_tree = self.tree(transcript, [('start', 'Start (s)', 90), ('end', 'End (s)', 90), ('text', 'Recognized English word', 650)])
        self.words_tree.bind('<Double-1>', self.edit_word)
        self.button(transcript, 'Suggest cut for selected words', self.cut_words).pack(anchor='w', pady=5)

        self.progress = ttk.Progressbar(outer, maximum=100)
        self.progress.pack(fill='x', pady=(8, 4))
        self.status = tk.StringVar(value='Ready. Videos stay on your computer. First speech analysis downloads a model with your consent.')
        ttk.Label(outer, textvariable=self.status, wraplength=1050).pack(anchor='w')
        self.after(100, self.poll)

    def button(self, parent, text, command):
        b = ttk.Button(parent, text=text, command=command)
        self.buttons.append(b)
        return b

    def tree(self, parent, columns):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True, pady=6)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show='headings', selectmode='extended')
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=50, stretch=key == columns[-1][0])
        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True)
        return tree

    def select(self):
        name = filedialog.askopenfilename(title='Select an English teaching video', filetypes=[('Video files', '*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mts'), ('All files', '*.*')])
        if name:
            self.source = Path(name)
            self.analysis = None
            self.refresh()
            self.file_label.configure(text=str(self.source))
            self.status.set('Selected video. Click Analyze video to find pauses and recognize speech.')

    def play_original(self):
        if self.source:
            os.startfile(str(self.source))

    def task(self, work, done):
        self.busy = True
        for b in self.buttons:
            b.configure(state='disabled')
        self.cancel_button.configure(state='normal')
        self.progress['value'] = 0
        self.processor = None
        def worker():
            try:
                self.processor = Processor(lambda p, t: self.events.put(('progress', (p, t))))
                self.events.put(('done', (done, work(self.processor))))
            except Exception as e:
                (CACHE / 'last-error.log').write_text(traceback.format_exc(), encoding='utf-8')
                self.events.put(('error', str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        # Drain without blocking the UI; ignore stale progress after completion.
        for _ in range(250):
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'progress':
                self.progress['value'], text = data
                self.status.set(text)
            else:
                self.busy = False
                for b in self.buttons:
                    b.configure(state='normal')
                self.cancel_button.configure(state='disabled')
                if kind == 'error':
                    self.status.set('Processing stopped. Original video is unchanged.')
                    messagebox.showerror('Processing stopped', data[-4000:])
                else:
                    callback, value = data
                    callback(value)
        self.after(100, self.poll)

    def analyze(self):
        if not self.source:
            return messagebox.showinfo('Select video', 'Select a video first.')
        if self.analysis and not messagebox.askyesno('Analyze again?', 'A new analysis replaces your current review and transcript corrections. Continue?'):
            return
        speech, model = self.flags['speech'].get(), self.model.get()
        consent = CACHE / ('consent-' + model)
        if speech and not consent.exists():
            if not messagebox.askyesno('Download local Whisper model?', f'The {model} model may download hundreds of MB (larger models over 1 GB) from Hugging Face on first use. No video or audio is uploaded. Files are cached inside this project. Allow model download?'):
                return
            consent.touch()
        self.status.set('Starting analysis…')
        self.task(lambda p: p.analyze(self.source, model, speech), self.analyzed)

    def analyzed(self, result):
        self.analysis = result
        self.refresh()
        self.progress['value'] = 100
        self.status.set(f"Analysis ready: {len(result['cuts'])} suggested cuts, {len(result['words'])} recognized words. Review before exporting.")

    def refresh(self):
        self.cut_tree.delete(*self.cut_tree.get_children())
        self.words_tree.delete(*self.words_tree.get_children())
        if self.analysis:
            for i, c in enumerate(self.analysis['cuts']):
                self.cut_tree.insert('', 'end', iid=str(i), values=('YES' if c.selected else 'Keep', f'{c.start:.2f}', f'{c.end:.2f}', c.reason, c.text))
            for i, w in enumerate(self.analysis['words']):
                self.words_tree.insert('', 'end', iid=str(i), values=(f"{w['start']:.2f}", f"{w['end']:.2f}", w['word']))

    def toggle_cut(self, event):
        if self.busy or not self.analysis:
            return
        item = self.cut_tree.identify_row(event.y)
        if item:
            c = self.analysis['cuts'][int(item)]
            c.selected = not c.selected
            self.cut_tree.set(item, 'use', 'YES' if c.selected else 'Keep')

    def clear_speech(self):
        if self.analysis:
            for c in self.analysis['cuts']:
                if not c.reason.startswith(('Silence', 'Trailing')):
                    c.selected = False
            self.refresh()

    def manual_cut(self):
        if not self.analysis:
            return
        start = simpledialog.askfloat('Add cut', 'Start time in seconds:', minvalue=0, maxvalue=self.analysis['duration'])
        if start is None:
            return
        end = simpledialog.askfloat('Add cut', 'End time in seconds:', minvalue=start+.01, maxvalue=self.analysis['duration'])
        if end is not None:
            self.analysis['cuts'].append(Cut(start, end, 'Manual cut', selected=True))
            self.refresh()

    def delete_cut(self):
        if self.analysis:
            for i in sorted(map(int, self.cut_tree.selection()), reverse=True):
                del self.analysis['cuts'][i]
            self.refresh()

    def edit_word(self, event):
        if self.busy or not self.analysis:
            return
        item = self.words_tree.identify_row(event.y)
        if item:
            word = self.analysis['words'][int(item)]
            new = simpledialog.askstring('Correct subtitle', 'Word / punctuation:', initialvalue=word['word'])
            if new is not None:
                word['word'] = new.strip()
                self.words_tree.set(item, 'text', word['word'])

    def cut_words(self):
        if self.analysis and self.words_tree.selection():
            words = [self.analysis['words'][int(i)] for i in self.words_tree.selection()]
            self.analysis['cuts'].append(Cut(min(w['start'] for w in words), max(w['end'] for w in words), 'Unnecessary speech (review)', ' '.join(w['word'] for w in words)))
            self.refresh()
            self.status.set('Added a speech suggestion. Select YES on the Suggested cuts tab to apply it.')

    def render(self, preview):
        if not self.analysis:
            return messagebox.showinfo('Analyze first', 'Select a video and analyze it first. Disable Whisper speech analysis for a quick edit without transcription.')
        options = {key: var.get() for key, var in self.flags.items()}
        options['watermark_text'] = self.watermark.get()
        try:
            options['watermark_size'] = int(self.fontsize.get())
            if not 16 <= options['watermark_size'] <= 72:
                raise ValueError()
        except (ValueError, tk.TclError):
            return messagebox.showerror('Watermark size', 'Enter a font size between 16 and 72.')
        if options['subtitles'] and not self.analysis['words']:
            return messagebox.showinfo('No transcript', 'Enable Whisper speech analysis and analyze again to create subtitles, or turn subtitles off.')
        if preview:
            output = CACHE / 'preview.mp4'
        else:
            name = filedialog.asksaveasfilename(title='Export edited video', initialdir=str(self.source.parent), initialfile=self.source.stem + '_edited.mp4', defaultextension='.mp4', filetypes=[('MP4 video', '*.mp4')])
            if not name:
                return
            output = Path(name)
            if output.suffix.lower() != '.mp4':
                return messagebox.showerror('MP4 filename', 'Choose an output filename ending in .mp4.')
            if output.resolve() == self.source.resolve():
                return messagebox.showerror('Protect original', 'Choose a different filename. Original videos are never overwritten.')
            if output.with_suffix('.srt').exists() and not messagebox.askyesno('Replace subtitles?', 'A matching SRT file exists. Allow replacement if subtitles are exported?'):
                return
        self.task(lambda p: p.render(self.source, output, self.analysis, options, preview), lambda result: self.rendered(result, preview))

    def rendered(self, output, preview):
        self.progress['value'] = 100
        self.status.set(f"{'Preview' if preview else 'Export'} ready: {output}")
        if preview:
            try:
                os.startfile(str(output))
            except OSError as e:
                messagebox.showerror('Open preview', str(e))
        else:
            messagebox.showinfo('Export complete', f'Saved:\n{output}\n\nSubtitles are selectable in compatible players; a matching SRT is also saved when available.')

    def save_review(self):
        if not self.analysis:
            return
        name = filedialog.asksaveasfilename(defaultextension='.json', initialfile='video-review.json', filetypes=[('Review report', '*.json')])
        if name:
            if Path(name).resolve() == self.source.resolve():
                return messagebox.showerror('Protect original', 'Choose a different filename for the review report.')
            result = dict(self.analysis, source=str(self.source), cuts=[asdict(c) for c in self.analysis['cuts']])
            Path(name).write_text(json.dumps(result, indent=2), encoding='utf-8')
            self.status.set('Review report saved (for reference; reopening a saved review is not supported).')

    def cancel(self):
        if self.processor:
            self.processor.cancel.set()
            self.status.set('Cancelling… Whisper stops after its current recognition segment or model download.')

    def close(self):
        if self.busy:
            self.cancel()
            messagebox.showinfo('Cancelling', 'Wait for processing to stop, then close the application.')
        else:
            self.destroy()


if __name__ == '__main__':
    Editor().mainloop()
