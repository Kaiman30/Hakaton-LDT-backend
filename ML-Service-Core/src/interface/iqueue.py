"""
Queue Interface - Strategy pattern implementation for message queue connectors.

Allows switching between different queue providers (Kafka, RabbitMQ, Redis, etc.)
while maintaining the same API.
"""

import uuid
from typing import Any, Dict, List, Optional, Union

from core.base_class.base_interface import BaseInterface
from core.base_class.protocols import IQueueConnector
from utils.observer import EventPublisher
from core.registry import register_interface


@register_interface("Queue")
class QueueInterface(BaseInterface, IQueueConnector):  # ← ДОБАВЛЯЕМ протокол!
    """
    High-level interface for message queue operations.

    Implements Strategy pattern - can switch between different queue providers
    (Kafka, RabbitMQ, Redis, etc.) transparently.
    """

    def __init__(
        self,
        worker: IQueueConnector,
        name: Optional[str] = None,
        event_publisher: Optional[EventPublisher] = None,
    ) -> None:
        """
        Initialize Queue interface.

        Args:
            worker: Queue connector instance (e.g., KafkaConnector)
            name: Interface name (defaults to worker name)
            event_publisher: Optional event publisher for observability
        """
        super().__init__(worker, name, event_publisher)

    @property
    def worker(self) -> IQueueConnector:
        """Get underlying queue connector"""
        return self._worker

    # ============ IQueueConnector protocol implementation ============

    async def publish(
        self,
        topic: str,
        datagram_id: str,
        data: Dict[str, Any],
        *,
        key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        format_type: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        Publish single message.
        
        Args:
            topic: Topic to publish to
            datagram_id: Unique message identifier
            data: Message payload
            key: Optional message key
            headers: Optional message headers
            format_type: Optional format type
            **kwargs: Additional arguments
        """
        await self._execute_with_tracking(
            "publish",
            self._worker.publish,
            topic,
            datagram_id,
            data,
            key=key,
            headers=headers,
            format_type=format_type,
            **kwargs,
            metadata={
                "topic": topic,
                "datagram_id": datagram_id,
                "has_key": key is not None,
                "has_headers": headers is not None,
            },
        )

    async def batch_publish(
        self,
        topic: str,
        messages: List[tuple],
        default_format: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        Publish batch of messages.

        Args:
            topic: Topic/queue name
            messages: List of message tuples (datagram_id, data, key, headers) or variations
            default_format: Default format for messages
            **kwargs: Additional arguments
        """
        await self._execute_with_tracking(
            "batch_publish",
            self._worker.batch_publish,
            topic,
            messages,
            default_format=default_format,
            **kwargs,
            metadata={"topic": topic, "count": len(messages)},
        )

    async def subscribe(
        self,
        topics: List[str],
        group_id: str,
        *,
        format_type: Optional[str] = None,
        auto_offset_reset: str = "earliest",
        **kwargs: Any,
    ) -> None:
        """
        Subscribe to topics.

        Args:
            topics: List of topics to subscribe to
            group_id: Consumer group ID
            format_type: Optional format type
            auto_offset_reset: Auto offset reset policy
            **kwargs: Additional arguments
        """
        await self._execute_with_tracking(
            "subscribe",
            self._worker.subscribe,
            topics,
            group_id,
            format_type=format_type,
            auto_offset_reset=auto_offset_reset,
            **kwargs,
            metadata={"topics": topics, "group_id": group_id},
        )

    async def consume(self) -> Dict[str, Any]:
        """
        Consume next message from queue.

        Returns:
            Message dict with 'payload' and metadata
        """
        return await self._execute_with_tracking(
            "consume",
            self._worker.consume,
            metadata={"operation": "consume_message"},
        )

    async def commit(self, message: Dict[str, Any], **kwargs: Any) -> None:
        """
        Commit specific message.

        Args:
            message: Message to commit
            **kwargs: Additional arguments
        """
        await self._execute_with_tracking(
            "commit",
            self._worker.commit,
            message,
            **kwargs,
            metadata={
                "consumer_group": getattr(self._worker, "group_id", "unknown"),
                "has_message": message is not None,
            },
        )

    # ============ Convenience methods (not part of protocol) ============

    async def publish_simple(
        self,
        topic: str,
        key: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        """
        Convenience method for simple publish (совместимо с documents_service).
        
        Args:
            topic: Topic to publish to
            key: Optional message key (used as datagram_id if not provided)
            headers: Optional message headers
            data: Message payload
            timeout: Optional timeout
            **kwargs: Additional arguments
        """
        # Используем key как datagram_id или генерируем новый
        datagram_id = key or str(uuid.uuid4())
        message_data = data or {}

        await self.publish(
            topic=topic,
            datagram_id=datagram_id,
            data=message_data,
            key=key,    
            headers=headers,
            **kwargs,
        )

    @property
    def name(self) -> str:
        """Get connector name - required by IQueueConnector protocol"""
        return self._name

    async def health_check(self) -> bool:
        """Check queue connectivity - required by IQueueConnector protocol"""
        return await self._execute_with_tracking(
            "health_check",
            self._worker.health_check,
            metadata={"check_type": "queue_connectivity"},
        )

    def is_healthy(self) -> bool:
        """Get cached health status - required by IQueueConnector protocol"""
        return self._worker.is_healthy()