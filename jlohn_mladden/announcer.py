import abc
from collections import defaultdict
from functools import cmp_to_key
import random
import re
import uuid
import time

import discord
from dotenv import load_dotenv
import pyttsx3

from jlohn_mladden.splorts_center import SplortsCenter
from jlohn_mladden.quip import Quip


class _dummy:
    last_update = 'Game over'


class Announcer(abc.ABC):

    def __init__(self, config, sound_manager=None):
        self._config = config
        self._sound_manager = sound_manager

        self.main_game = config['calling_for'].lower()
        self.calling_for = self.main_game
        self.last_pbps = []

    @property
    def playoff_mode(self):
        return self.main_game == 'playoffs'

    def on_update(self):
        def callback(schedule, index):
            if not schedule:
                return []

            schedule = self.on_schedule(schedule)

            game = self.choose_game(schedule, index)
            pbp = game and game.last_update
            if not pbp:
                return []
            skip_quips = self.on_play_by_play(pbp, game, schedule)
            if skip_quips:
                return []
            if pbp.lower() in self.last_pbps:
                return []
            quips = Quip.say_quips(pbp, game)
            for quip in quips:
                quip = self.preprocess_quip(quip)
                if quip in self.last_pbps:
                    continue
                self.last_pbps.append(quip.lower())
                print(quip)
                self.enqueue_message(quip)

            self.last_pbps = self.last_pbps[-4:]  # redundancy
            self.speak()

        return callback

    def choose_game(self, schedule, index):
        """
        Upon receiving the stream data update and full schedule, select 
        """
        return schedule.get(index[self.calling_for])

    def on_schedule(self, schedule):
        """
        Override with custom logic to process a new schedule update.
        """
        return schedule

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

    def change_channel(self, schedule):
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
        update = f'Thank you for listening to this {self.calling_for} broadcast. Over to the {next_game.home_team_nickname}.'
        update = self.preprocess_quip(update)
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

        if 'Game over' in message and 'game over' in self.last_pbps:
            game_id = self.change_channel(schedule)
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
        update = self.preprocess_quip(self.splorts_center.next_update())
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

    def choose_game(self, schedule, index):
        """
        Overridden for playoff mode.
        """
        cur_game = schedule.get(index.get(self.calling_for, ''))
        if not self.playoff_mode:
            return cur_game

        point_diff = 0
        if cur_game:
            # we are already calling a game, only check if we need to switch
            # stickiness algo by sakimori
            # switch if blowout (4+ run differential)
            # choose game that's tied in 9th and not 0 0
            # always watch extra innings
            games = sorted(schedule.values(), key=lambda g: g.inning)
            for game in games:
                if game.game_complete:
                    continue
                if game.inning > 8:
                    # extra innings, h*ck ya
                    self.voice.say(f"We have extra innings with {game.away_team_nickname} at {game.home_team_nickname}. Switching broadcast.")
                    self.calling_for = game.home_team_nickname.lower()
                    self.current_game_id = game.id_
                    self.choose_voice()
                    return game
                if game.inning == 8 and game.point_differential == 0 and game.home_score > 0:
                    # tied in the ninth
                    self.voice.say(f"We've a tie game in the ninth, over to {game.away_team_nickname} at {game.home_team_nickname}.")
                    self.calling_for = game.home_team.nickname.lower()
                    self.current_game_id = game.id_
                    self.choose_voice()
                    return game

            if game.point_differential <= 4:
                return cur_game
            # there's a blow out, fall through to general game selection
            self.voice.say(f"Things seem to be getting out of hand.")

        # playoff algo by sakimori
        # TODO sort games by series end
        games = [g for g in schedule.values() if not g.game_complete]
        if not games:
            return _dummy()

        # if any games are not in the 9th inning, remove the ones that are
        # repeat for 8th
        games = sorted(games, key=lambda g: g.inning)
        if games[0].inning < 7:
            games = [g for g in games if g.inning < 7]

        # take game with closests score
        # break ties by losing team having highest number of regular season wins
        def compare(a, b):
            if a.point_differential < b.point_differential:
                return -1
            if a.point_differential > b.point_differential:
                return 1
            a_wins = a.home_wins if a.home_score < a.away_score else b.away_wins
            b_wins = b.home_wins if b.home_score < b.away_score else b.away_wins
            if a_wins < b_wins:
                return -1
            if a_wins > b_wins:
                return 1
            return 0

        games = sorted(games, key=cmp_to_key(compare))
        new_game = games[0]
        self.calling_for = new_game.home_team_nickname.lower()
        self.current_game_id = new_game.id_
        # if there was a blowout, mention the switch
        if cur_game and cur_game.point_differential > 4:
            self.voice.say(f'Over to {new_game.away_team_nickname} at {new_game.home_team_nickname}.')
        self.choose_voice()
        return new_game



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
