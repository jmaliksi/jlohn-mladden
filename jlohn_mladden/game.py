import time

from blaseball_mike.stream_model import StreamData
from blaseball_mike.events import stream_events

BLASE_MAP = {
    0: 'first',
    1: 'second',
    2: 'third',
}


class GameSnapshot(object):

    def __init__(self, game, **kwargs):
        self.id_ = game.id
        self.day = game.day
        self.season = game.season
        self.away_team = game.away_team_name
        self.home_team = game.home_team_name
        self.away_score = game.away_score
        self.home_score = game.home_score

        self.inning = game.inning
        self.batting_change = kwargs.get('batting_change', False)
        self.top_of_inning = game.top_of_inning

        self.team_at_bat = game.at_bat_team_nickname
        self.pitching_team = game.pitching_team_nickname
        self.at_bat = game.current_batter_name
        self.pitching = game.current_pitcher_name

        self.strikes = game.at_bat_strikes
        self.balls = game.at_bat_balls
        self.outs = game.half_inning_outs

        self.on_blase = ['', '', '']
        self.bases_occupied = game.baserunner_count
        if game.baserunner_count > 0:
            for name, base in zip(game.base_runner_names, game.bases_occupied):
                self.on_blase[base] = name or 'runner'

        self.shame = game.shame
        self.last_update = game.last_update
        self.snapshot_at = time.time()

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


class GamesWatcher(object):

    def __init__(self):
        self._games = {}
        self._subscribers = []

    def update(self, schedule):
        if not schedule:
            return
        # snapshot games each cycle to avoid stale values on interpolation
        game_updates = {}
        index = {}
        for id_, game in schedule.games.items():
            batting_change = False
            if id_ in self._games:
                last_update = self._games[id_]
                batting_change = game.top_of_inning != last_update.top_of_inning
            index[game.home_team_nickname.lower()] = id_
            index[game.away_team_nickname.lower()] = id_
            game_updates[id_] = GameSnapshot(game, batting_change=batting_change)

        for subscriber in self._subscribers:
            subscriber(game_updates, index)

        self._games = game_updates

    def subscribe(self, on_update):
        """
        Register subscriber callback to be called when a new schedule comes in.
        Callback will be called with (schedule, index) where index is a dictionary
        {team_nick_name: game_id}.
        """
        self._subscribers.append(on_update)

    async def stream(self):
        async for event in stream_events():
            if not event:
                continue
            stream_data = StreamData(event)
            self.update(stream_data.games.schedule)
