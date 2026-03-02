"""
Messaging broker for inter-tier communication.
Supports both ZeroMQ and Redis backends.
"""

import zmq
import redis
import json
import asyncio
from typing import Optional, Callable, Dict, Any, List
from enum import Enum
import structlog


logger = structlog.get_logger(__name__)


class MessagingBackend(Enum):
    """Supported messaging backends."""
    ZEROMQ = "zeromq"
    REDIS = "redis"


class MessagingBroker:
    """
    Unified messaging broker for system-wide pub/sub communication.
    
    Provides abstraction over ZeroMQ or Redis for inter-tier messaging.
    """
    
    def __init__(
        self,
        backend: str = "zeromq",
        zmq_host: str = "127.0.0.1",
        zmq_port: int = 5555,
        redis_host: str = "127.0.0.1",
        redis_port: int = 6379,
    ):
        """
        Initialize messaging broker.
        
        Args:
            backend: "zeromq" or "redis"
            zmq_host: ZeroMQ host
            zmq_port: ZeroMQ port
            redis_host: Redis host
            redis_port: Redis port
        """
        self.backend = MessagingBackend(backend.lower())
        self.zmq_host = zmq_host
        self.zmq_port = zmq_port
        self.redis_host = redis_host
        self.redis_port = redis_port
        
        self.context: Optional[zmq.Context] = None
        self.publishers: Dict[str, Any] = {}
        self.subscribers: Dict[str, Any] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.redis_pubsub: Optional[redis.client.PubSub] = None
        
    async def initialize(self):
        """Initialize the messaging backend."""
        if self.backend == MessagingBackend.ZEROMQ:
            await self._init_zeromq()
        elif self.backend == MessagingBackend.REDIS:
            await self._init_redis()
        logger.info("messaging_broker_initialized", backend=self.backend.value)
    
    async def _init_zeromq(self):
        """Initialize ZeroMQ context."""
        self.context = zmq.Context()
    
    async def _init_redis(self):
        """Initialize Redis client."""
        self.redis_client = redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            decode_responses=True,
        )
        self.redis_pubsub = self.redis_client.pubsub()
    
    async def publish(self, topic: str, message: Dict[str, Any]):
        """
        Publish message to topic.
        
        Args:
            topic: Topic name
            message: Message data (will be JSON serialized)
        """
        if self.backend == MessagingBackend.ZEROMQ:
            await self._publish_zeromq(topic, message)
        elif self.backend == MessagingBackend.REDIS:
            await self._publish_redis(topic, message)
    
    async def _publish_zeromq(self, topic: str, message: Dict[str, Any]):
        """Publish via ZeroMQ."""
        if topic not in self.publishers:
            socket = self.context.socket(zmq.PUB)
            socket.bind(f"tcp://{self.zmq_host}:{self.zmq_port}")
            self.publishers[topic] = socket
        
        socket = self.publishers[topic]
        msg_json = json.dumps(message)
        socket.send_multipart([topic.encode(), msg_json.encode()])
        logger.debug("message_published", backend="zeromq", topic=topic)
    
    async def _publish_redis(self, topic: str, message: Dict[str, Any]):
        """Publish via Redis."""
        msg_json = json.dumps(message)
        self.redis_client.publish(topic, msg_json)
        logger.debug("message_published", backend="redis", topic=topic)
    
    async def subscribe(self, topic: str, callback: Callable):
        """
        Subscribe to topic with callback.
        
        Args:
            topic: Topic name
            callback: Async callback function(message: Dict)
        """
        if self.backend == MessagingBackend.ZEROMQ:
            await self._subscribe_zeromq(topic, callback)
        elif self.backend == MessagingBackend.REDIS:
            await self._subscribe_redis(topic, callback)
        logger.info("subscribed_to_topic", backend=self.backend.value, topic=topic)
    
    async def _subscribe_zeromq(self, topic: str, callback: Callable):
        """Subscribe via ZeroMQ."""
        socket = self.context.socket(zmq.SUB)
        socket.connect(f"tcp://{self.zmq_host}:{self.zmq_port}")
        socket.subscribe(topic.encode())
        self.subscribers[topic] = socket
        
        # Start background listening task
        asyncio.create_task(self._zeromq_listen(topic, socket, callback))
    
    async def _zeromq_listen(self, topic: str, socket, callback: Callable):
        """Background listener for ZeroMQ."""
        loop = asyncio.get_event_loop()
        while True:
            try:
                topic_bytes, msg_json = await loop.run_in_executor(
                    None, socket.recv_multipart
                )
                msg = json.loads(msg_json.decode())
                await callback(msg)
            except Exception as e:
                logger.error("zeromq_listen_error", topic=topic, error=str(e))
                await asyncio.sleep(1)
    
    async def _subscribe_redis(self, topic: str, callback: Callable):
        """Subscribe via Redis."""
        self.redis_pubsub.subscribe(topic)
        
        # Start background listening task
        asyncio.create_task(self._redis_listen(topic, callback))
    
    async def _redis_listen(self, topic: str, callback: Callable):
        """Background listener for Redis."""
        for message in self.redis_pubsub.listen():
            try:
                if message["type"] == "message":
                    msg = json.loads(message["data"])
                    await callback(msg)
            except Exception as e:
                logger.error("redis_listen_error", topic=topic, error=str(e))
                await asyncio.sleep(1)
    
    async def close(self):
        """Close all connections."""
        if self.backend == MessagingBackend.ZEROMQ:
            for socket in self.publishers.values():
                socket.close()
            for socket in self.subscribers.values():
                socket.close()
            if self.context:
                self.context.term()
        elif self.backend == MessagingBackend.REDIS:
            if self.redis_pubsub:
                self.redis_pubsub.close()
            if self.redis_client:
                self.redis_client.close()
        logger.info("messaging_broker_closed")
