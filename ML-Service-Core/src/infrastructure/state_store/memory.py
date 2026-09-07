from collections import defaultdict

from .models import ConnectorStatus
from .repository import StateRepository


class MemoryStateRepository(StateRepository):

    def __init__(self):
        self._timeline = defaultdict(list)
        self._current = {}

    def save(self, status: ConnectorStatus):
        self._current[status.connector] = status
        self._timeline[status.connector].append(status)

    def get(self, connector):
        return self._current.get(connector)

    def snapshot(self):
        return dict(self._current)

    def timeline(self, connector):
        return list(self._timeline.get(connector, []))