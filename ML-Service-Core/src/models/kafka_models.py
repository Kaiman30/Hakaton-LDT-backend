"""
Kafka API Data Models
Separated from connector to improve code organization and maintainability
"""

from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass
from datetime import datetime


@dataclass
class KafkaMessageKey:
    """Represents the key of a Kafka message"""
    key: Optional[str] = None
    
    def to_bytes(self) -> Optional[bytes]:
        """Convert key to bytes for Kafka serialization"""
        return self.key.encode("utf-8") if self.key else None


@dataclass
class KafkaMessageHeaders:
    """Represents the headers of a Kafka message"""
    headers: Optional[Dict[str, str]] = None
    
    def to_kafka_format(self) -> Optional[List[tuple]]:
        """Convert headers to Kafka-compatible format"""
        if not self.headers:
            return None
        return [(k, str(v).encode("utf-8")) for k, v in self.headers.items()]


@dataclass
class KafkaMessageValue:
    """Represents the value/payload of a Kafka message"""
    value: Union[Dict[str, Any], str]
    
    def to_serialized_bytes(self) -> bytes:
        """Serialize value to bytes using connector's serializer"""
        import json
        if isinstance(self.value, str):
            return self.value.encode("utf-8")
        return json.dumps(self.value, ensure_ascii=False).encode("utf-8")


@dataclass
class KafkaPublishRequest:
    """Request model for publishing messages to Kafka"""
    topic: str
    value: Union[Dict[str, Any], str]
    key: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    datagram_id: Optional[str] = None
    
    def to_kafka_params(self) -> Dict[str, Any]:
        """Convert to parameters for Kafka producer"""
        kafka_headers = None
        if self.headers:
            kafka_headers = [(k, str(v).encode("utf-8")) for k, v in self.headers.items()]
        
        return {
            "topic": self.topic,
            "value": self.value,  # Will be serialized by connector's serializer
            "key": self.key,
            "headers": kafka_headers
        }


@dataclass
class KafkaBatchPublishRequest:
    """Request model for batch publishing messages to Kafka"""
    topic: str
    messages: List[Dict[str, Any]]  # List of message dicts with key/value/headers
    
    def to_kafka_format(self) -> List[Dict[str, Any]]:
        """Convert to Kafka-compatible format for batch publishing"""
        result = []
        for msg in self.messages:
            kafka_msg = {
                "value": msg.get("value"),
                "key": msg.get("key"),
                "headers": None
            }
            if msg.get("headers"):
                kafka_msg["headers"] = [(k, str(v).encode("utf-8")) for k, v in msg["headers"].items()]
            result.append(kafka_msg)
        return result


@dataclass
class KafkaSubscribeRequest:
    """Request model for subscribing to Kafka topics"""
    topics: List[str]
    group_id: str
    auto_offset_reset: str = "earliest"
    
    def to_kafka_params(self) -> Dict[str, Any]:
        """Convert to parameters for Kafka consumer"""
        return {
            "topics": self.topics,
            "group_id": self.group_id,
            "auto_offset_reset": self.auto_offset_reset
        }


@dataclass
class KafkaReceivedMessage:
    """Model representing a received Kafka message with metadata"""
    payload: Dict[str, Any]  # The actual message data
    kafka_key: Optional[str]  # Key of the message
    kafka_topic: str  # Topic name
    kafka_partition: int  # Partition number
    kafka_offset: int  # Offset in partition
    kafka_headers: Optional[Dict[str, str]]  # Message headers
    kafka_timestamp: Optional[int]  # Timestamp of the message
    kafka_timestamp_type: Optional[int]  # Type of timestamp
    
    @classmethod
    def from_kafka_message(cls, kafka_msg: Dict[str, Any]) -> 'KafkaReceivedMessage':
        """Create KafkaReceivedMessage from raw Kafka message dict"""
        return cls(
            payload=kafka_msg["payload"],
            kafka_key=kafka_msg["kafka_key"],
            kafka_topic=kafka_msg["kafka_topic"],
            kafka_partition=kafka_msg["kafka_partition"],
            kafka_offset=kafka_msg["kafka_offset"],
            kafka_headers=kafka_msg["kafka_headers"],
            kafka_timestamp=kafka_msg["kafka_timestamp"],
            kafka_timestamp_type=kafka_msg["kafka_timestamp_type"]
        )


@dataclass
class KafkaCommitRequest:
    """Request model for committing Kafka message offsets"""
    topic: str
    partition: int
    offset: int
    
    def to_kafka_params(self) -> Dict[str, Any]:
        """Convert to parameters for Kafka consumer commit"""
        from aiokafka.structs import TopicPartition
        
        tp = TopicPartition(self.topic, self.partition)
        return {
            "offsets": {tp: self.offset + 1}
        }


@dataclass
class KafkaHealthCheckResponse:
    """Response model for Kafka health check"""
    is_healthy: bool
    error: Optional[str] = None