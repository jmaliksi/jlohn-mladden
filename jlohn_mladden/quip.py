from collections import defaultdict
import random
import re

from jlohn_mladden import utils


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
        res = []
        for quip in quips:
            res.append(cls(**quip))
        return res

    @classmethod
    def say_quips(cls, play_by_play, game):
        pbp = play_by_play
        if re.match(f'{game.winning_team} \d+, {game.losing_team} \d+', pbp):
            pbp = f'Game over.'
        quips = utils.UniqueList()
        for term, quip_list in cls.before_index.items():
            for quip in quip_list:
                if term in pbp and random.random() < quip.chance and eval(quip.conditions, {}, {'pbp': pbp, 'game': game, 'utils': utils}):
                    quips.append(quip.evaluate(pbp, game))

        quips.append(pbp)

        for term, quip_list in cls.after_index.items():
            for quip in quip_list:
                if term in pbp and random.random() < quip.chance and eval(quip.conditions, {}, {'pbp': pbp, 'game': game, 'utils': utils}):
                    quips.append(quip.evaluate(pbp, game))

        return quips

    def evaluate(self, play_by_play, game):
        args = {}
        for key, equation in self.args.items():
            args[key] = eval(equation, {}, {'game': game, 'utils': utils})

        return random.choice(self.phrases).format(**args)
