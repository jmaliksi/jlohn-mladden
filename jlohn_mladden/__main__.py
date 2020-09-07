import asyncio

from blaseball_mike.events import stream_events
from blaseball_mike.stream_model import StreamData
import yaml

from jlohn_mladden.quip import Quip
from jlohn_mladden.sounds import SoundManager
from jlohn_mladden.game import GamesWatcher
from jlohn_mladden.announcer import TTSAnnouncer


def main():
    with open('config/quips.yaml', 'r') as f:
        y = yaml.load(f)
        sound_manager = SoundManager(y)

        quips = Quip.load(y['quips'])

        announcer_config = y['announcer']

        loop = asyncio.get_event_loop()
        if announcer_config['announcer_type'] == 'discord':
            pass  # TODO
        elif announcer_config['announcer_type'] == 'tts':
            announcer = TTSAnnouncer(announcer_config, sound_manager)
        else:
            raise Exception('Unsupported announcer type')

        game_watcher = GamesWatcher()
        game_watcher.subscribe(announcer.on_update())

        loop.create_task(game_watcher.stream())
        loop.run_forever()


if __name__ == '__main__':
    main()
