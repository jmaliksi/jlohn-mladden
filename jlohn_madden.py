import time
import random
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from collections import defaultdict
import ujson
import pyttsx3
import requests
import pydub
import pydub.utils
import pyaudio
import sys
import yaml

import asyncio
import pprint
from aiohttp_sse_client import client as sse_client
from aiohttp.client_exceptions import ClientPayloadError

import os

import discord
from dotenv import load_dotenv


BLASE_MAP = {
    0: 'first',
    1: 'second',
    2: 'third',
}

class SplortsCenter(object):

    def __init__(self, season, day):
        self.season = season
        self.day = day
        self.updates = []

    def load_ticker(self):
        res = requests.get('https://www.blaseball.com/database/globalEvents')
        if res.status_code != 200:
            return
        for msg in res.json():
            self.updates.append(msg['msg'].lower())

    def load_results(self):
        res = requests.get(f'https://www.blaseball.com/database/games?season={self.season - 1}&day={self.day - 1}')
        if res.status_code != 200:
            return
        for game in res.json():
            home_team = game['homeTeamName']
            away_team = game['awayTeamName']

            home_score = game['homeScore']
            away_score = game['awayScore']
            winning_team = home_team if home_score > away_score else away_team
            winning_score = home_score if home_score > away_score else away_score
            losing_team = home_team if home_score < away_score else away_team
            losing_score = home_score if home_score < away_score else away_score

            self.updates.append(
                f'{away_team} at {home_team}, game {game["seriesIndex"]} of {game["seriesLength"]}. ' +
                f'The {winning_team} defeat the {losing_team} {winning_score} to {losing_score}'
            )

            for outcome in game.get('outcomes', []):
                self.updates.append(outcome)

    def next_update(self):
        if not self.updates:
            self.updates = []
            self.load_results()
            self.load_ticker()
            self.updates = sorted(self.updates, key=lambda _: random.random())
            self.updates.insert(0, f'And that concludes day {self.day} of season {self.season}. Welcome to Splorts Center.')
        return self.updates.pop(0)


class UniqueList(list):
    def append(self, value):
        if value not in self:
            super(UniqueList, self).append(value)


class SoundManager(object):

    def __init__(self, sounds):
        self.audio_cues = {}
        for name, config in sounds.items():
            try:
                self.audio_cues[name] = pydub.AudioSegment.from_wav(config['file']) + config['volume']
            except Exception:
                pass

        self.sound_pool = ThreadPoolExecutor(max_workers=10)
        self._pyaudio = pyaudio.PyAudio()

    def execute_sound(self, key, delay=0):
        if delay:
            time.sleep(delay)
        if key not in self.audio_cues:
            return
        seg = self.audio_cues[key]
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

    def run_sound(self):
        p = pyaudio.PyAudio()
        stream = None
        try:
            while True:
                try:
                    sample = self.q.get()
                    stream = p.open(
                        format=p.get_format_from_width(sample.sample_width),
                        channels=sample.channels,
                        rate=sample.frame_rate,
                        output=True,
                    )
                    for chunk in pydub.utils.make_chunks(sample, 500):
                        stream.write(chunk._data)
                        thread.sleep(0)
                finally:
                    stream.stop_stream()
                    stream.close()
        finally:
            p.terminate()

    def play_sound(self, key, delay=0):
        print(key, file=sys.stderr)
        self.sound_pool.submit(self.execute_sound, key, delay=delay)


class utils(object):
    @staticmethod
    def pronounce_inning(inning):
        if inning == 1:
            return 'first'
        if inning == 2:
            return 'second'
        if inning == 3:
            return 'third'
        return '{}th'.format(inning)

    @staticmethod
    def plural(v):
        return 's' if v > 1 else ''


class PlayerNames(object):

    def __init__(self):
        self._players = {}

    def get(self, id_):
        if id_ in self._players:
            return self._players[id_]
        try:
            player = requests.get('https://blaseball.com/database/players?ids={}'.format(id_))
            name = player.json()[0].get('name')
            if name:
                self._players[id_] = name
            return name
        except Exception:
            return None
        return None


player_names = PlayerNames()


class BlaseballGlame(object):

    def __init__(self):
        self.game_logs = []
        self.id_ = ''
        self.away_team = ''
        self.home_team = ''
        self.at_bat = ''
        self.pitching = ''
        self.inning = 1
        self.top_of_inning = False
        self.batting_change = False
        self.away_score = 0
        self.home_score = 0
        self.strikes = 0
        self.balls = 0
        self.outs = 0
        self.on_blase = ['', '', '']
        self.bases_occupied = 0
        self.team_at_bat = ''
        self.shame = False

        self.last_update = ''
        self.day = 0
        self.season = 0

    @property
    def has_runners(self):
        return self.on_blase != ['', '', '']

    @property
    def runners(self):
        runners = []
        for i, player in enumerate(self.on_blase):
            if player:
                runners.append((player, BLASE_MAP[i]))
        return runners

    def update(self, msg):
        """msg should already be json, filtered to the appropriate team"""
        pbp = msg['lastUpdate']
        # self.game_logs.append(pbp)
        # self.sound_effects(pbp)

        self.id_ = msg['id']
        self.day = msg['day'] + 1
        self.season = msg['season'] + 1
        self.away_team = msg['awayTeamName']
        self.home_team = msg['homeTeamName']
        self.away_score = msg['awayScore']
        self.home_score = msg['homeScore']

        self.inning = msg['inning'] + 1
        self.batting_change = msg['topOfInning'] != self.top_of_inning
        self.top_of_inning = msg['topOfInning']  # true means away team at bat

        self.team_at_bat = msg['awayTeamNickname'] if self.top_of_inning else msg['homeTeamNickname']
        self.pitching_team = msg['homeTeamNickname'] if self.top_of_inning else msg['awayTeamNickname']
        at_bat = msg['awayBatterName'] if self.top_of_inning else msg['homeBatterName']
        pitching = msg['homePitcherName'] if self.top_of_inning else msg['awayPitcherName']
        # sometimes these just clear out, don't overwrite if cached
        self.at_bat = at_bat or self.at_bat
        self.pitching = pitching or self.pitching

        self.strikes = msg['atBatStrikes']
        self.balls = msg['atBatBalls']
        self.outs = msg['halfInningOuts']

        self.on_blase = ['', '', '']
        self.bases_occupied = msg['baserunnerCount']
        if msg['baserunnerCount'] > 0:
            for pid, base in zip(msg['baseRunners'], msg['basesOccupied']):
                player_name = player_names.get(pid)
                self.on_blase[base] = player_name or 'runner'
        self.shame = msg['shame']
        print(
            'away: {} {}'.format(self.away_team, self.away_score),
            'home: {} {}'.format(self.home_team, self.home_score),
            'inning: {}'.format(self.inning),
            'at_bat: {}'.format(self.at_bat),
            'pitching: {}'.format(self.pitching),
            's|b|o {}|{}|{}'.format(self.strikes, self.balls, self.outs),
            self.on_blase,
            file=sys.stderr,
        )
        self.last_update = pbp
        return pbp


class Quip(object):

    before_index = defaultdict(list)
    after_index = defaultdict(list)

    def __init__(self,
                 phrases,
                 trigger_before=None,
                 trigger_after=None,
                 args=None,
                 chance=1.0,
                 conditions='True'):
        self.phrases = phrases
        self.trigger_before = trigger_before or []
        self.trigger_after = trigger_after or []
        self.args = args or {}
        self.chance = chance
        self.conditions = conditions

        for trigger in self.trigger_before:
            self.before_index[trigger].append(self)
        for trigger in self.trigger_after:
            self.after_index[trigger].append(self)

    @classmethod
    def load(cls, quips):
        """json list"""
        res = []
        for quip in quips:
            res.append(cls(**quip))
        return res

    @classmethod
    def say_quips(cls, play_by_play, game):
        play_by_play = play_by_play.lower()
        quips = UniqueList()
        for term, quip_list in cls.before_index.items():
            for quip in quip_list:
                if term in play_by_play and random.random() < quip.chance and eval(quip.conditions, {}, {'game': game, 'utils': utils}):
                    quips.append(quip.evaluate(play_by_play, game))

        quips.append(play_by_play)

        for term, quip_list in cls.after_index.items():
            for quip in quip_list:
                if term in play_by_play and random.random() < quip.chance and eval(quip.conditions, {}, {'game': game, 'utils': utils}):
                    quips.append(quip.evaluate(play_by_play, game))

        return quips

    def evaluate(self, play_by_play, game):
        args = {}
        for key, equation in self.args.items():
            args[key] = eval(equation, {}, {'game': game, 'utils': utils})
        return random.choice(self.phrases).format(**args)

class Announcer(object):
    def __init__(self, calling_for='Fridays', announcer_config=None):
        self.main_game = calling_for
        self.calling_for = calling_for
        self.calling_game = BlaseballGlame()
        self.last_pbps = []
        if announcer_config:
            self.main_game = announcer_config['calling_for']
            self.calling_for = announcer_config['calling_for']


class TTSAnnouncer(Announcer):
    def __init__(self, calling_for='Fridays', announcer_config=None):
        super().__init__(calling_for=calling_for, announcer_config=announcer_config)
        self.calling_game = BlaseballGlame()
        self.voice = pyttsx3.init(debug=True)
        self.voice.connect('started-utterance', self.sound_effect)

        voice_ids = set([self.voice.getProperty('voice')])
        if announcer_config:
            system_voices = [v.id for v in self.voice.getProperty('voices')]
            for voice in announcer_config.get('friends', []):
                if voice in system_voices:
                    voice_ids.add(voice)
        self.voice_ids = list(voice_ids)
        self.voice.setProperty('voice', random.choice(self.voice_ids))

        self.splorts_center = None
        self.enable_splorts_center = announcer_config.get('enable_splorts_center')

    def on_message(self):
        def callback(message, last_update_time):
            if not message:
                return []
            for game in message:
                if self.calling_for in (game['awayTeamNickname'], game['homeTeamNickname']):
                    pbp = self.calling_game.update(game)
                    if not pbp:
                        break

                    if 'Play ball!' in pbp:
                        self.switch_voice()

                    if 'Game over' in pbp and 'game over.' in self.last_pbps:
                        has_game = self.switch_game(message)
                        if not has_game:
                            self.engage_splorts_center()
                        return

                    if time.time() * 1000 - last_update_time > 3000:
                        # play catch up if we're lagging by focusing on play by play
                        quips = [pbp.lower()]
                    else:
                        quips = Quip.say_quips(pbp, self.calling_game)

                    for quip in quips:
                        if quip in self.last_pbps:
                            continue
                        self.last_pbps.append(quip)
                        print(quip)
                        self.voice.say(quip, quip)

                    break
            self.voice.runAndWait()
            self.last_pbps = self.last_pbps[-4:]  # avoid last 4 redundancy
        return callback

    def engage_splorts_center(self):
        if not self.enable_splorts_center:
            return
        if not self.splorts_center or \
                self.calling_game.day != self.splorts_center.day or \
                self.calling_game.season != self.splorts_center.season:
            self.splorts_center = SplortsCenter(
                self.calling_game.season,
                self.calling_game.day,
            )
            self.switch_voice()
        update = self.splorts_center.next_update()
        print(update)
        sound_manager.play_sound('splorts_update')
        self.voice.say(update)
        self.voice.runAndWait()

    def switch_game(self, schedule):
        candidates = []
        for game in schedule:
            pbp = game.get('lastUpdate')
            if pbp == 'Game over.':
                continue
            candidates.append(game)
        if not candidates:
            self.calling_for = self.main_game
            return None

        # choose game with closest score
        candidates = sorted(candidates, key=lambda x: abs(x.get('homeScore', 0) - x.get('awayScore', 0)))

        next_game = candidates[0].get('homeTeamNickname')
        update = f'Thank you for listening to this {self.calling_for} broadcast. Over to {next_game}.'
        print(update)
        self.voice.say(update)
        self.voice.runAndWait()
        self.switch_voice()

        self.calling_for = next_game
        self.last_pbps = []
        return self.calling_for

    def switch_voice(self):
        cur_voice = self.voice.getProperty('voice')
        voices = [v for v in self.voice_ids if v != cur_voice]
        if voices:
            self.voice.setProperty('voice', random.choice(voices))

    def sound_effect(self, name):
        if not name:
            return
        for cue in sound_cues:
            if cue['trigger'] in name:
                sound_manager.play_sound(
                    random.choice(cue['sounds']),
                    delay=cue['delay'],
                )


class DiscordAnnouncer(Announcer):

    def __init__(self, calling_for='Millennials', announcer_config=None):
        super().__init__(calling_for=calling_for, announcer_config=announcer_config)
        self.messages = []
        load_dotenv()
        self.token = os.getenv("DISCORD_TOKEN")
        self.channel_id = int(os.getenv("DISCORD_CHANNEL"))
        self.voice_channel_id = int(os.getenv("DISCORD_VOICE_CHANNEL", 0))
        self.client = discord.Client()
        self.ready = False
        if announcer_config:
            self.prefix = announcer_config.get('discord_prefix', "")

        @self.client.event
        async def on_ready():
            print("Connected to Discord as {}.".format(self.client.user.name))
            self.channel = self.client.get_channel(self.channel_id)
            if self.voice_channel_id:
                self.voice_channel = self.client.get_channel(self.voice_channel_id)
                await self.voice_channel.connect()
            self.ready = True
        
        self.client.loop.create_task(self.say_all())
    
    async def start(self):
        await self.client.start(self.token)

    async def say_all(self):
        while True:
            if self.messages:
                for message in self.messages:
                    await self.say("{}{}".format(self.prefix, message))
                self.messages.clear()
            await asyncio.sleep(1)

    async def say(self, message):
        if self.ready:
            print("Announcing: {}".format(message))
            await self.channel.send(message)

    def on_message(self):
        def callback(message, last_update_time):
            if not message:
                return []
            for game in message:
                if self.calling_for in (game['awayTeamNickname'], game['homeTeamNickname']):
                    pbp = self.calling_game.update(game)
                    if not pbp:
                        break

                    if time.time() * 1000 - last_update_time > 2300:
                        # play catch up if we're lagging by focusing on play by play
                        quips = [pbp]
                    else:
                        quips = Quip.say_quips(pbp, self.calling_game)

                    for quip in quips:
                        if quip in self.last_pbps:
                            continue
                        self.last_pbps.append(quip)
                        # print(quip)
                        self.messages.append(quip)
                    break
            self.last_pbps = self.last_pbps[-4:]  # avoid last 4 redundancy
        return callback


async def sse_loop(cb):
    retry_delay = 0.1
    while True:
        try:
            async with sse_client.EventSource('https://www.blaseball.com/events/streamData') as src:
                async for event in src:
                    retry_delay = 0.1  # reset backoff
                    payload = ujson.loads(event.data)
                    # TODO set up logger
                    schedule = payload.get('value', {}).get('games', {}).get('schedule')
                    if not schedule:
                        continue
                    # whyyyyy
                    # last_update_time = payload['value'].get('lastUpdateTime', 0)
                    # delta = time.time() * 1000 - last_update_time
                    # print(delta, file=sys.stderr)
                    # if delta < 4000:
                    cb(schedule, time.time() * 1000)
        except (ConnectionError, TimeoutError, ClientPayloadError):
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 300)


def main(announcer_config):
    loop = asyncio.get_event_loop()
    if announcer_config['announcer_type'] == "discord":
        announcer = DiscordAnnouncer(calling_for='Millennials')
        loop.create_task(announcer.start())
    elif announcer_config['announcer_type'] == "tts":
        announcer = TTSAnnouncer(announcer_config=announcer_config)
    else:
        raise Exception("Unsupported announcer type")
    loop.create_task(sse_loop(announcer.on_message()))
    loop.run_forever()


def test():
    announcer = TTSAnnouncer(calling_for='Fridays')

    test_dump = [
        'gameDataUpdate',
        {
            'schedule': [
                {
                    u'id': u'4d26c148-3fe8-4b9a-9f64-7c10a0607423',
                    u'atBatBalls': 0,
                    u'atBatStrikes': 0,
                    u'awayBatter': u'',
                    u'awayBatterName': u'',
                    u'awayOdds': 0.5585154403765049,
                    u'awayPitcher': u'bf122660-df52-4fc4-9e70-ee185423ff93',
                    u'awayPitcherName': u'Walton Sports',
                    u'awayScore': 6,
                    u'awayStrikes': 3,
                    u'awayTeam': u'a37f9158-7f82-46bc-908c-c9e2dda7c33b',
                    u'awayTeamBatterCount': 11,
                    u'awayTeamColor': u'#6388ad',
                    u'awayTeamEmoji': u'0x1F450',
                    u'awayTeamName': u'Hawaii Fridays',
                    u'awayTeamNickname': u'Fridays',
                    u'baseRunners': [u'd8ee256f-e3d0-46cb-8c77-b1f88d8c9df9'],
                    u'baserunnerCount': 1,
                    u'basesOccupied': [0],
                    u'day': 93,
                    u'finalized': False,
                    u'gameComplete': False,
                    u'gameStart': True,
                    u'halfInningOuts': 2,
                    u'halfInningScore': 0,
                    u'homeBatter': u'',
                    u'homeBatterName': u'',
                    u'homeOdds': 0.44148455962349503,
                    u'homePitcher': u'd0d7b8fe-bad8-481f-978e-cb659304ed49',
                    u'homePitcherName': u'Adalberto Tosser',
                    u'homeScore': 0,
                    u'homeStrikes': 3,
                    u'homeTeam': u'8d87c468-699a-47a8-b40d-cfb73a5660ad',
                    u'homeTeamBatterCount': 5,
                    u'homeTeamColor': u'#593037',
                    u'homeTeamEmoji': u'0x1F980',
                    u'homeTeamName': u'Baltimore Crabs',
                    u'homeTeamNickname': u'Crabs',
                    u'inning': 2,
                    u'isPostseason': False,
                    u'lastUpdate': u"someone was incinerated",
                    u'outcomes': [],
                    u'phase': 3,
                    u'rules': u'4ae9d46a-5408-460a-84fb-cbd8d03fff6c',
                    u'season': 2,
                    u'seriesIndex': 1,
                    u'seriesLength': 3,
                    u'shame': False,
                    u'statsheet': u'ec7b5639-ddff-4ffa-8181-87710bbd02cd',
                    u'terminology': u'b67e9bbb-1495-4e1b-b517-f1444b0a6c8b',
                    u'topOfInning': True,
                u'weather': 11}
            ]
        },
    ]

    announcer.on_message()(ujson.dumps(test_dump[1]['schedule']))
    return


with open('./quips.yaml', 'r') as __f:
    __y = yaml.load(__f)
    sound_manager = SoundManager(__y['sounds'])
    sound_cues = __y['sound_cues']
    Quip.load(__y['quips'])
    __announcer_config = __y['announcer']


if __name__ == '__main__':
    main(__announcer_config)
