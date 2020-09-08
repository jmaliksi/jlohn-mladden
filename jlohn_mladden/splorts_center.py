import random
from blaseball_mike.models import GlobalEvent, Game

class SplortsCenter(object):

    def __init__(self, season, day):
        self.season = season
        self.day = day
        self.updates = []

    def load_ticker(self):
        events = GlobalEvent.load()
        for msg in events:
            self.updates.append('Welcome to Splorts Center. ' + msg.msg.lower())

    def load_results(self):
        if self.day == 1:
            return
        games = Game.load_by_day(self.season, self.day)
        for game in games.values():
            self.updates.append(
                'Welcome to Splorts Center. ' +
                f'{game.away_team_name} at {game.home_team_name}, game {game.series_index} of {game.series_length}. ' +
                f'The {game.winning_team_nickname} defeat the {game.losing_team_nickname} {game.winning_score} to {game.losing_score}.'
            )

            for outcome in game.outcomes:
                self.updates.append('Welcome to Splorts Center. ' + outcome)

    def next_update(self):
        if not self.updates:
            self.updates = []
            self.load_results()
            self.load_ticker()
            self.updates = sorted(self.updates, key=lambda _: random.random())
            self.updates.insert(0, f'And that concludes day {self.day} of season {self.season}. Welcome to Splorts Center. ')
        return self.updates.pop(0)
