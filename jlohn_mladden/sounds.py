from concurrent.futures import ThreadPoolExecutor, TimeoutError
import os.path
import random
import time
import sys

import pyaudio
import pydub


class SoundManager(object):

    def __init__(self, config):
        self.sound_effects = {}
        sound_root_folder = config['sound_root_folder']
        for name, c in config['sounds'].items():
            path = os.path.join(sound_root_folder, c['file'])
            try:
                self.sound_effects[name] = pydub.AudioSegment.from_wav(path) + c['volume']
            except Exception:
                pass

        self.sound_pool = ThreadPoolExecutor(max_workers=10)
        self._pyaudio = pyaudio.PyAudio()

        self.sound_cues = config['sound_cues']

    def execute_sound(self, key, delay=0):
        if key not in self.sound_effects:
            return
        if delay:
            time.sleep(delay)
        seg = self.sound_effects[key]
        stream = self._pyaudio.open(
            format=self._pyaudio.get_format_from_width(seg.sample_width),
            channels=seg.channels,
            rate=seg.frame_rate,
            output=True,
        )
        try:
            for chunk in pydub.utils.make_chunks(seg, 500):
                stream.write(chunk._data)
        finally:
            stream.stop_stream()
            stream.close()

    def play_sound(self, key, delay=0):
        print(key, file=sys.stderr)
        self.sound_pool.submit(self.execute_sound, key, delay=delay)

    def cue_sound(self, message):
        if not message:
            return
        for cue in self.sound_cues:
            if cue['trigger'] in message:
                self.play_sound(
                    random.choice(cue['sounds']),
                    delay=cue.get('delay', 0.0),
                )
