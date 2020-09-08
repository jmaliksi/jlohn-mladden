import abc
from collections import defaultdict
import random
import re
import uuid
import time

import discord
from dotenv import load_dotenv
import pyttsx3

from jlohn_mladden.splorts_center import SplortsCenter
from jlohn_mladden.quip import Quip


class Announcer(abc.ABC):

    def __init__(self, config, sound_manager=None):
        self._config = config
        self._sound_manager = sound_manager

        self.main_game = config['calling_for'].lower()
        self.calling_for = self.main_game
        self.last_pbps = []

    def on_update(self):
        def callback(schedule, index):
            if not schedule or index.get(self.calling_for, '') not in schedule:
                return []

            self.on_schedule(schedule)

            game = schedule.get(index[self.calling_for])
            pbp = game and game.last_update
            if not pbp:
                return []
            skip_quips = self.on_play_by_play(pbp, game, schedule)
            if skip_quips:
                return []
            quips = Quip.say_quips(pbp, game)
            for quip in quips:
                quip = self.preprocess_quip(quip)
                if quip in self.last_pbps:
                    continue
                self.last_pbps.append(quip)
                print(quip)
                self.enqueue_message(quip)

            self.last_pbps = self.last_pbps[-4:]  # redundancy
            self.speak()

        return callback

    def on_schedule(self, schedule):
        """
        Override with custom logic to process a new schedule update.
        """
        pass

    def on_play_by_play(self, message, game, schedule):
        """
        Override with custom logic to process play by play for calling_game, ie voice switching
        Return True to skip processing the rest of this quip cycle (ie if you're overriding
        everything)
        """
        return False

    @abc.abstractmethod
    def enqueue_message(self, message):
        """
        Override with logic to enqueue a message to your output of choice.
        """
        pass

    def speak(self):
        """
        Override to tell your output to flush enqueued messages as appropriate
        """
        pass

    def preprocess_quip(self, quip):
        """
        Override with custom processing of a quip before it is sent to output, ie for localization
        """
        return quip


class TTSAnnouncer(Announcer):

    def __init__(self, config, sound_manager=None):
        super().__init__(config, sound_manager)
        self.voice = pyttsx3.init(debug=True)
        self.voice.connect('started-utterance', self.sound_effect)

        voice_ids = set([self.voice.getProperty('voice')])
        system_voices = [v.id for v in self.voice.getProperty('voices')]
        for voice in config.get('friends', []):
            if voice in system_voices:
                voice_ids.add(voice)
        self.voice_ids = list(voice_ids)
        self.voice.setProperty('voice', random.choice(self.voice_ids))

        self.current_game_id = ''
        self.splorts_center = None
        self.enable_splorts_center = config.get('enable_splorts_center', False)

        self.voice_localizations = defaultdict(list)
        for name, locs in config.get('localization').items():
            for loc in locs:
                self.voice_localizations[name].append((re.compile(loc['pattern']), loc['replace']))

    def sound_effect(self, name):
        if self._sound_manager:
            self._sound_manager.cue_sound(name)

    def enqueue_message(self, message):
        self.voice.say(message, message)

    def speak(self):
        self.voice.runAndWait()

    def choose_voice(self):
        """
        Deterministcally choose a voice based on the current game ID, should be random enough.
        """
        cur_voice = self.voice.getProperty('voice')
        if not self.current_game_id:
            cur_voice = self.voice.getProperty('voice')
            voices = [v for v in self.voice_ids if v != cur_voice]
            if voices:
                self.voice.setProperty('voice', random.choice(voices))
            return
        dex = uuid.UUID(self.current_game_id).int % len(self.voice_ids)
        if cur_voice != self.voice_ids[dex]:
            self.voice.setProperty('voice', self.voice_ids[dex])

    def choose_game(self, schedule):
        if not self.current_game_id:
            # first iteration, hasn't been hydrated yet
            return ''

        if self.current_game_id in schedule and not schedule[self.current_game_id].game_complete:
            return self.current_game_id

        candidates = []
        for game in schedule.values():
            if not game.game_complete:
                candidates.append(game)
        if not candidates:
            self.current_game_id = ''
            self.calling_for = self.main_game
            return ''

        self.splorts_center = None

        candidates = sorted(candidates, key=lambda g: abs(g.home_score - g.away_score))
        next_game = candidates[0]
        update = f'Thank you for listening to this {self.calling_for} broadcast. Over to {next_game.home_team_nickname}.'
        print(update)
        self.voice.say(update)
        self.voice.runAndWait()

        self.current_game_id = next_game.id_
        self.calling_for = next_game.home_team_nickname.lower()
        self.choose_voice()

        self.last_pbps = []
        return next_game.id_

    def on_play_by_play(self, message, game, schedule):
        if self.current_game_id != game.id_:
            # new game, switch voice
            self.current_game_id = game.id_
            self.choose_voice()

        if 'Game over' in message and 'game over.' in self.last_pbps:
            game_id = self.choose_game(schedule)
            if not game_id:
                self.engage_splorts_center(game)
                return True
        return False

    def engage_splorts_center(self, game):
        if not self.enable_splorts_center:
            return
        if not self.splorts_center or game.day != self.splorts_center.day or game.season != self.splorts_center.season:
            self.splorts_center = SplortsCenter(game.season, game.day)
            self.choose_voice()
        update = self.splorts_center.next_update()
        print(update)
        self._sound_manager.play_sound('splorts_update')
        self.voice.say(update)
        self.voice.runAndWait()

    def preprocess_quip(self, quip):
        cur_voice = self.voice.getProperty('voice')
        localizations = self.voice_localizations.get('global') + self.voice_localizations.get(cur_voice, [])
        for pattern, sub in localizations:
            quip = re.sub(pattern, sub, quip)
        return quip


class DiscordAnnouncer(Announcer):

    def __init__(self, config, sound_manager=None):
        super().__init__(config, sound_manager)
        self.messages = []
        load_dotenv()
        self.token = os.getenv('DISCORD_TOKEN')
        self.channel_id = int(os.getenv('DISCORD_CHANNEL'))
        self.voice_channel_id = int(os.getenv('DISCORD_VOICE_CHANNEL', 0))
        self.client = discord.Client()
        self.ready = False
        self.prefix = config.get('discord_prefix', '')

        @self.client.event
        async def on_ready():
            print('Connected to Discord as {}.'.format(self.client.user.name))
            self.channel = self.client.get_channel(self.channel_id)
            if self.voice_channel_id:
                self.voice_channel = self.client.get_channel(self.voice_channel_id)
                await self.voice_channel.connect()
            self.ready = True

        self.client.loop.create_task(self.say_all())

    async def say_all(self):
        while True:
            if self.messages:
                for message in self.messages:
                    await self.say('{}{}'.format(self.prefix, message))
                self.messages.clear()
            await asyncio.sleep(1)

    async def say(self, message):
        if self.ready:
            print('Announcing: {}'.format(message))
            await self.channel.send(message)

    def enqueue_message(self, message):
        self.messages.append(message)
