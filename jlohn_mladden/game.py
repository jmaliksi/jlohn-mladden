import time

from blaseball_mike.models import Fight
from blaseball_mike.stream_model import StreamData
from blaseball_mike.events import stream_events

BLASE_MAP = {
    0: 'first',
    1: 'second',
    2: 'third',
    3: 'fourth',
}


class GameSnapshot(object):

    def __init__(self, game, **kwargs):
        self.id_ = game.id
        self.day = game.day
        self.season = game.season
        self.away_team = game.away_team_name
        self.home_team = game.home_team_name
        self.away_team_nickname = game.away_team_nickname
        self.home_team_nickname = game.home_team_nickname
        self.away_score = game.away_score
        self.home_score = game.home_score
        self.point_differential = abs(self.home_score - self.away_score)

        self.winning_team = self.away_team_nickname if self.away_score > self.home_score else self.home_team_nickname
        self.losing_team = self.away_team_nickname if self.away_score < self.home_score else self.home_team_nickname

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

        base_count = game.away_bases if game.top_of_inning else game.home_bases
        self.base_count = base_count
        self.on_blase = [''] * max(base_count, len(game.base_runner_names))
        self.bases_occupied = game.baserunner_count
        if game.baserunner_count > 0:
            for name, base in zip(game.base_runner_names, game.bases_occupied):
                try:
                    self.on_blase[base] = name or 'runner'
                except Exception:
                    pass

        standings = kwargs.get('standings', {})
        self.series_length = game.series_length
        self.series_index = game.series_index
        self.home_wins = standings.wins.get(game._home_team_id, 0)
        self.away_wins = standings.wins.get(game._away_team_id, 0)

        self.home_series_wins = 0
        self.away_series_wins = 0
        if kwargs.get('postseason'):
            matchups = kwargs['postseason'].get('matchups', [])
            for matchup in matchups:
                if matchup['awayTeam'] == game._away_team_id:
                    self.away_series_wins = matchup['awayWins']
                if matchup['homeTeam'] == game._home_team_id:
                    self.home_series_wins = matchup['homeWins']

        self.game_complete = game.game_complete
        self.shame = game.shame
        self.last_update = ' '.join([game.last_update, game.score_update]).strip()
        self.score_update = game.score_update
        self.score_ledger = game.score_ledger
        self.snapshot_at = time.time()

        self.game_type = 'game'
        self.play_count = game.play_count

    @property
    def has_runners(self):
        return self.bases_occupied > 0

    @property
    def runners(self):
        runners = []
        for i, player in enumerate(self.on_blase):
            if player:
                runners.append((player, BLASE_MAP[i]))
        return runners


class BossFight(GameSnapshot):

    def __init__(self, game, **kwargs):
        super().__init__(game, **kwargs)
        self.game_type = 'fight'


class GamesWatcher(object):

    def __init__(self):
        self._games = {}
        self._subscribers = []

    def update(self, games, raw=None, fights=None):
        schedule = games and games.schedule
        if not schedule:
            return
        raw = raw or {}
        # snapshot games each cycle to avoid stale values on interpolation
        game_updates = {}
        index = {}

        for id_, game in schedule.games.items():
            game_updates[id_] = self._create_snapshot(id_, game, index, games, raw)

        if fights:
            for id_, game in fights.boss_fights.items():
                game_updates[id_] = self._create_snapshot(id_, game, index, games, raw)

        for subscriber in self._subscribers:
            subscriber(game_updates, index)

        self._games = game_updates

    def _create_snapshot(self, id_, game, index, games, raw):
        batting_change = False
        weather_change = False
        if id_ in self._games:
            last_update = self._games[id_]
            batting_change = game.top_of_inning != last_update.top_of_inning
            #weather_change = game.weather != last_update.weather
        index[game.home_team_nickname.lower()] = id_
        index[game.away_team_nickname.lower()] = id_
        Clz = BossFight if isinstance(game, Fight) else GameSnapshot
        return Clz(
            game,
            batting_change=batting_change,
            standings=games.standings,
            postseason=raw.get('games', {}).get('postseason', {}),
        )

    def subscribe(self, on_update):
        """
        Register subscriber callback to be called when a new schedule comes in.
        Callback will be called with (schedule, index) where index is a dictionary
        {team_nick_name: game_id}.
        """
        self._subscribers.append(on_update)

    async def stream(self, url='https://www.blaseball.com/events/streamData'):
        async for event in stream_events(url=url):
            if not event:
                continue
            stream_data = StreamData(event)
            self.update(stream_data.games, raw=event, fights=stream_data.fights)
