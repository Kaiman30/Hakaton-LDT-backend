"""
Async Kafka Connector - Pure async implementation using aiokafka for no-GIL
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

from core.base_class.base_connector import QueueConnector
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.kafka_models import (
        KafkaPublishRequest,
        KafkaBatchPublishRequest,
        KafkaSubscribeRequest,
        KafkaReceivedMessage,
        KafkaCommitRequest,
        KafkaHealthCheckResponse,
        KafkaMessageHeaders
    )


@register_connector("Kafka")
@dependence_connector("Queue")
class KafkaConnector(QueueConnector):
    """
    Native asyncio-friendly Kafka connector using aiokafka.
    Pure async implementation without threading.
    """

    def __init__(
        self,
        bootstrap_servers: List[str],
        group_id: Optional[str] = None,
        auto_offset_reset: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        consumer_poll_timeout: float = 1.0,
    ) -> None:
        super().__init__(name="kafka")
        self.bootstrap_servers = bootstrap_servers
        self.logger = logger or logging.getLogger(__name__)
        self.consumer_poll_timeout = consumer_poll_timeout

        self._producer: Optional[AIOKafkaProducer] = None
        self._consumer: Optional[AIOKafkaConsumer] = None

        # Флаг и топики для подписки
        self._subscribed_topics: List[str] = []
        self._group_id = group_id
        self._consumer_running = False
        self._auto_offset_reset = auto_offset_reset or "earliest"

        # Async queue для сообщений
        self._message_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

    @classmethod
    def from_config(cls, config: Any, **kwargs) -> "KafkaConnector":
        """
        Create KafkaConnector from config.

        Args:
            config: Settings object with config.kafka
            **kwargs: Additional arguments (ignored for compatibility)

        Returns:
            Configured KafkaConnector instance
        """
        servers_raw = config.kafka.bootstrap_servers
        if isinstance(servers_raw, str):
            bootstrap_servers = [s.strip() for s in servers_raw.split(",") if s.strip()]
        else:
            bootstrap_servers = list(servers_raw)

        return cls(
            bootstrap_servers=bootstrap_servers,
            group_id=config.kafka.group_id,
            auto_offset_reset=config.kafka.auto_offset_reset,
            logger=logging.getLogger(__name__),
            consumer_poll_timeout=config.kafka.consumer_poll_timeout,
        )

    # ----------------- Инициализация / shutdown -----------------

    async def initialize(self) -> None:
        """Создать асинхронные Kafka клиенты."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: v.encode("utf-8")
            if isinstance(v, str)
            else json.dumps(v, ensure_ascii=False).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k is not None else None,
        )
        await self._producer.start()
        self.logger.info("Kafka producer initialized")

    async def shutdown(self) -> None:
        """Остановить producer и consumer."""
        if self._consumer_running and self._consumer:
            await self._consumer.stop()
            self._consumer_running = False
            self.logger.info("Kafka consumer stopped")

        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
            self.logger.info("Kafka producer closed")

    # ----------------- Публикация -----------------

    async def publish(
        self,
        topic: str,
        datagram_id: str,
        data: Dict[str, Any],
        format_type: Optional[str] = None,
        key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        **_: Any,
    ) -> None:
        """
        Асинхронная публикация JSON-сообщения.
        data - ваш словарь, который будет отправлен как есть.
        headers - заголовки сообщения Kafka (опционально)
        """
        if self._producer is None:
            raise RuntimeError("Kafka producer not initialized")

        # Ленивый импорт для избежания циклических зависимостей
        from models.kafka_models import KafkaPublishRequest

        # Create request model using the new data model
        publish_request = KafkaPublishRequest(
            topic=topic,
            value=data,
            key=key,
            headers=headers,
            datagram_id=datagram_id
        )

        # Extract parameters using the model
        kafka_params = publish_request.to_kafka_params()

        await self._producer.send_and_wait(
            kafka_params["topic"],
            value=kafka_params["value"],
            key=kafka_params["key"],
            headers=kafka_params["headers"]
        )

    async def batch_publish(
        self,
        topic: str,
        messages: List[
            tuple
        ],  # (datagram_id, data_dict, key, headers) или (data_dict, key, headers) или (data_dict, key)
        default_format: Optional[str] = None,
        **_: Any,
    ) -> None:
        """
        Батч-отправка JSON-сообщений.
        """
        if self._producer is None:
            raise RuntimeError("Kafka producer not initialized")

        for item in messages:
            if len(item) == 4:
                datagram_id, data, key, headers = item
            elif len(item) == 3:
                if isinstance(item[2], dict):  # headers
                    data, key, headers = item
                    datagram_id = None
                else:  # (datagram_id, data, key)
                    datagram_id, data, key = item
                    headers = None
            elif len(item) == 2:
                data, key = item
                datagram_id = None
                headers = None
            else:
                raise ValueError(
                    "Each message tuple must be (data, key), (data, key, headers), (datagram_id, data, key), or (datagram_id, data, key, headers)"
                )

            # Ленивый импорт для избежания циклических зависимостей
            from models.kafka_models import KafkaPublishRequest

            # Create request model for each message
            publish_request = KafkaPublishRequest(
                topic=topic,
                value=data,
                key=key,
                headers=headers,
                datagram_id=datagram_id
            )

            # Extract parameters using the model
            kafka_params = publish_request.to_kafka_params()

            await self._producer.send_and_wait(
                kafka_params["topic"],
                value=kafka_params["value"],
                key=kafka_params["key"],
                headers=kafka_params["headers"]
            )

    # ----------------- Подписка / Consumer -----------------

    async def subscribe(
        self,
        topics: List[str],
        group_id: str,
        format_type: Optional[str] = None,
        auto_offset_reset: str = "earliest",
        **_: Any,
    ) -> None:
        """
        Запустить асинхронный consumer.
        Сообщения будут приходить в self._message_queue как Dict.
        """
        if self._consumer_running:
            raise RuntimeError("Consumer already running")

        # Ленивый импорт для избежания циклических зависимостей
        from models.kafka_models import KafkaSubscribeRequest

        # Create request model using the new data model
        subscribe_request = KafkaSubscribeRequest(
            topics=topics,
            group_id=group_id,
            auto_offset_reset=auto_offset_reset
        )

        # Extract parameters using the model
        kafka_params = subscribe_request.to_kafka_params()

        self._subscribed_topics = kafka_params["topics"]
        self._group_id = kafka_params["group_id"]

        self._consumer = AIOKafkaConsumer(
            bootstrap_servers=self.bootstrap_servers,
            group_id=kafka_params["group_id"],
            auto_offset_reset=kafka_params["auto_offset_reset"],
            enable_auto_commit=False,  # Отключаем авто-подтверждение
            value_deserializer=lambda v: json.loads(v.decode("utf-8"))
            if v is not None
            else None,
            key_deserializer=lambda k: k.decode("utf-8") if k is not None else None,
            max_poll_interval_ms=300000,      # 5 минут
            session_timeout_ms=30000,         # 30 секунд
            heartbeat_interval_ms=10000,      # 10 секунд
        )

        # Подписываемся на топики до старта consumer
        self._consumer.subscribe(topics=kafka_params["topics"])

        await self._consumer.start()

        self._consumer_running = True

        # Запускаем внутренний цикл обработки сообщений
        asyncio.create_task(self._consumer_loop())

    async def _consumer_loop(self) -> None:
        """Внутренний асинхронный цикл получения сообщений"""
        self.logger.info(
            f"Kafka consumer started: topics={self._subscribed_topics}, group={self._group_id}"
        )

        try:
            while self._consumer_running:
                # Проверяем, что consumer действительно запущен и готов к работе
                if not self._consumer or not self._consumer._client or not self._consumer._coordinator:
                    self.logger.warning("Consumer is not properly initialized, skipping poll cycle")
                    await asyncio.sleep(1)
                    continue

                # Получаем сообщения
                msg_batch = await self._consumer.getmany(
                    timeout_ms=int(self.consumer_poll_timeout * 1000),
                    max_records=10  # Ограничиваем количество сообщений за раз
                )

                for tp, messages in msg_batch.items():
                    for msg in messages:
                        try:
                            # msg.value теперь уже Dict[str, Any] благодаря value_deserializer
                            raw_message_dict = msg.value

                            # Извлекаем заголовки из сообщения Kafka
                            headers_dict = {}
                            if msg.headers:
                                for header_key, header_value in msg.headers:
                                    # Декодируем байты в строку, если нужно
                                    if isinstance(header_value, bytes):
                                        try:
                                            headers_dict[header_key] = (
                                                header_value.decode("utf-8")
                                            )
                                        except UnicodeDecodeError:
                                            # Если не удается декодировать, сохраняем как base64
                                            import base64

                                            headers_dict[header_key] = (
                                                base64.b64encode(
                                                    header_value
                                                ).decode("utf-8")
                                            )
                                    else:
                                        headers_dict[header_key] = header_value

                            # Ленивый импорт для избежания циклических зависимостей
                            from models.kafka_models import KafkaReceivedMessage

                            # Create received message model
                            received_message = KafkaReceivedMessage(
                                payload=raw_message_dict,
                                kafka_key=msg.key,
                                kafka_topic=tp.topic,  # Добавляем информацию о топике
                                kafka_partition=msg.partition,
                                kafka_offset=msg.offset,
                                kafka_headers=headers_dict,  # Добавляем заголовки
                                kafka_timestamp=msg.timestamp,
                                kafka_timestamp_type=msg.timestamp_type,
                            )

                            # Convert to dict for backward compatibility
                            message_with_meta = received_message.__dict__

                            await self._message_queue.put(message_with_meta)
                        except Exception as e:
                            self.logger.error(
                                f"Error processing message: {e}", exc_info=True
                            )
        except Exception as e:
            self.logger.error(f"Error in consumer loop: {e}", exc_info=True)
        finally:
            if self._consumer:
                try:
                    await self._consumer.stop()
                except Exception as e:
                    self.logger.error(f"Error stopping consumer: {e}")

    async def consume(self) -> Dict[str, Any]:
        """
        Асинхронно получить следующее сообщение (из очереди).
        Блокирует до появления сообщения.
        Возвращает словарь с 'payload' и метаданными Kafka.
        """
        message_with_meta = await self._message_queue.get()
        self.logger.debug(f"Got kafka message: \n{message_with_meta}")
        return message_with_meta

    async def commit(self, message: Dict[str, Any], **kwargs: Any) -> None:
        """
        Commit specific message to Kafka.
        message - сообщение, которое нужно подтвердить
        """
        from aiokafka.structs import TopicPartition

        if not self._consumer:
            raise RuntimeError("Kafka consumer not initialized")

        # Ленивый импорт для избежания циклических зависимостей
        from models.kafka_models import KafkaReceivedMessage

        # Create received message model from the raw message dict
        received_message = KafkaReceivedMessage.from_kafka_message(message)

        # Получаем partition и offset из сообщения
        partition = received_message.kafka_partition
        offset = received_message.kafka_offset
        topic = received_message.kafka_topic  # Получаем топик из сообщения

        if partition is None or offset is None:
            self.logger.warning("Cannot commit message: missing partition or offset")
            return

        if not topic:
            # Если топик не указан в сообщении, используем первый из подписанных
            topic = self._subscribed_topics[0] if self._subscribed_topics else None
            if not topic:
                self.logger.warning("Cannot commit message: no subscribed topics")
                return

        # Создаем TopicPartition объект
        tp = TopicPartition(topic, partition)

        # Подтверждаем конкретный offset
        await self._consumer.commit({tp: offset + 1})
        self.logger.debug(
            f"Committed offset {offset + 1} for topic {topic}, partition {partition}"
        )

    async def health_check(self) -> bool:
        """
        Простейшая проверка доступности брокера:
        - продюсер должен быть инициализирован
        - пытаемся отправить ping
        """
        try:
            if not self._producer:
                # Ленивый импорт для избежания циклических зависимостей
                from models.kafka_models import KafkaHealthCheckResponse
                response = KafkaHealthCheckResponse(is_healthy=False, error="Producer not initialized")
                self._set_health(response.is_healthy)
                return response.is_healthy

            # Лёгкая проверка: отправляем пустое сообщение
            await self._producer.send_and_wait("health-check-topic", "ping")
            response = KafkaHealthCheckResponse(is_healthy=True)
            self._set_health(response.is_healthy)
            return response.is_healthy
        except Exception as exc:
            self.logger.warning(f"Kafka health check failed: {exc}")
            # Ленивый импорт для избежания циклических зависимостей
            from models.kafka_models import KafkaHealthCheckResponse
            response = KafkaHealthCheckResponse(is_healthy=False, error=str(exc))
            self._set_health(response.is_healthy)
            return response.is_healthy
