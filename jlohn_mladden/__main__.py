import asyncio
import click

from blaseball_mike.events import stream_events
from blaseball_mike.stream_model import StreamData
import yaml

from jlohn_mladden.quip import Quip
from jlohn_mladden.sounds import SoundManager
from jlohn_mladden.game import GamesWatcher
from jlohn_mladden.announcer import DiscordAnnouncer, TTSAnnouncer


@click.command()
@click.option('--calling_for', default=None)
@click.option('--test', is_flag=True)
@click.option('--test_ascii', is_flag=True)
def main(calling_for, test, test_ascii):
    with open('config/quips.yaml', 'r') as f:
        y = yaml.load(f)
        sound_manager = SoundManager(y)

        quips = Quip.load(y['quips'])

        announcer_config = y['announcer']
        if calling_for:
            announcer_config['calling_for'] = calling_for

        loop = asyncio.get_event_loop()
        if announcer_config['announcer_type'] == 'discord':
            announcer = DiscordAnnouncer(announcer_config, None)
            loop.create_task(announcer.start())
        elif announcer_config['announcer_type'] == 'tts':
            announcer = TTSAnnouncer(announcer_config, sound_manager)
        else:
            raise Exception('Unsupported announcer type')

        game_watcher = GamesWatcher()
        game_watcher.subscribe(announcer.on_update())

        stream_url = 'https://www.blaseball.com/events/streamData'
        if test:
            stream_url = 'http://localhost:8080/streamData'
        loop.create_task(game_watcher.stream(url=stream_url))
        loop.run_forever()


if __name__ == '__main__':
    main()
