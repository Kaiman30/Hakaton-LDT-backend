# ports/inbound/broker/queue.py
"""
Queue Interface - Strategy pattern implementation.
Uses DTOs from dto.py for type-safe communication.
"""

from typing import Optional

from ports.inbound.broker.dto import (
    PublishRequest,
    PublishResponse,
    BatchPublishRequest,
    BatchPublishResponse,
    SubscribeRequest,
    ConsumeRequest,
    ConsumeResponse,
    CommitRequest,
    CommitResponse,
)
from ports.protocols import IQueueConnector
from core.base_class.base_interface import BaseInterface
from core.registry import InterfaceRegistry
from core.runtime.event_bus import RuntimeEventBus


@InterfaceRegistry.register("Queue")
class QueueInterface(BaseInterface[IQueueConnector], IQueueConnector):
    """
    High-level interface for message queue operations.
    Implements Strategy pattern with DTO-based communication.
    """

    def __init__(
        self,
        worker: IQueueConnector,
        name: Optional[str] = None,
        event_bus: Optional[RuntimeEventBus] = None,
    ) -> None:
        super().__init__(worker, name, event_bus)

    @property
    def worker(self) -> IQueueConnector:
        return self._worker

    # ============ IQueueConnector Implementation ============

    async def publish(self, request: PublishRequest) -> PublishResponse:
        """Publish message with observability."""
        return await self._execute_with_tracking(
            "publish",
            self._worker.publish,
            request,
            metadata={
                "topic": request.topic,
                "has_key": request.key is not None,
                "has_headers": bool(request.headers),
                "priority": request.priority.value,
            },
        )

    async def batch_publish(self, request: BatchPublishRequest) -> BatchPublishResponse:
        """Batch publish with observability."""
        return await self._execute_with_tracking(
            "batch_publish",
            self._worker.batch_publish,
            request,
            metadata={
                "topic": request.topic,
                "messages_count": len(request.messages),
                "has_default_format": request.default_format is not None,
            },
        )

    async def subscribe(self, request: SubscribeRequest) -> None:
        """Subscribe with observability."""
        await self._execute_with_tracking(
            "subscribe",
            self._worker.subscribe,
            request,
            metadata={
                "topics": request.topics,
                "group_id": request.group_id,
                "auto_offset_reset": request.auto_offset_reset,
            },
        )

    async def consume(self, request: ConsumeRequest) -> ConsumeResponse:
        """Consume with observability."""
        return await self._execute_with_tracking(
            "consume",
            self._worker.consume,
            request,
            metadata={
                "topic": request.topic,
                "group_id": request.group_id,
                "max_messages": request.max_messages,
                "timeout": request.timeout,
                "auto_commit": request.auto_commit,
            },
        )

    async def commit(self, request: CommitRequest) -> CommitResponse:
        """Commit with observability."""
        return await self._execute_with_tracking(
            "commit",
            self._worker.commit,
            request,
            metadata={
                "message_ids_count": len(request.message_ids),
                "consumer_group": request.group_id,
                "topic": request.topic,
            },
        )

    # ============ Protocol Required ============

    @property
    def name(self) -> str:
        return self._name

    @property
    def healthy(self) -> bool:
        return self._worker.healthy

    async def check_health(self) -> bool:
        return await self._execute_with_tracking(
            "check_health",
            self._worker.check_health,
            metadata={"check_type": "queue_connectivity"},
        )

    async def initialize(self) -> None:
        await self._worker.initialize()

    async def shutdown(self) -> None:
        await self._worker.shutdown()