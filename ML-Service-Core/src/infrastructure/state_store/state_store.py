from .models import ConnectorStatus
from .repository import StateRepository


class InfrastructureStateStore:

    def __init__(self, repository: StateRepository):
        self.repository = repository

    def update(self, status: ConnectorStatus):
        self.repository.save(status)

    def current(self, connector: str):
        return self.repository.get(connector)

    def snapshot(self):
        return self.repository.snapshot()

    def timeline(self, connector: str):
        return self.repository.timeline(connector)