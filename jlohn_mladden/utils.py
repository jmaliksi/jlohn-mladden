class UniqueList(list):
    def append(self, value):
        if value not in self:
            super(UniqueList, self).append(value)


def pronounce_inning(inning):
    if inning == 1:
        return 'first'
    if inning == 2:
        return 'second'
    if inning == 3:
        return 'third'
    return '{}th'.format(inning)


def plural(v):
    return 's' if v > 1 else ''
