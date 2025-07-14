import os
import redis
import logging
import json
from typing import AsyncGenerator
import asyncio

logger = logging.getLogger(__name__)

class RedisHelper:
    BROADCAST_CHANNEL = "broadcasts"
    AUTHORIZED_CHATS_KEY = "authorized_chats"

    def __init__(self):
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise RuntimeError("REDIS_URL environment variable is not set")
        self.client = redis.Redis.from_url(redis_url, decode_responses=True)  # decode=True for str payloads

    def is_authorized(self, chat_id: int) -> bool:
        """
        Check if a chat is authorized to use the bot.

        :param chat_id: The ID of the chat to check.
        :return: True if the chat is authorized, False otherwise.
        """
        return self.client.sismember(self.AUTHORIZED_CHATS_KEY, chat_id)

    def authorize_chat(self, chat_id: int) -> None:
        """
        Authorize a chat to use the bot.

        :param chat_id: The ID of the chat to add to the redis authorized set.
        """
        self.client.sadd(self.AUTHORIZED_CHATS_KEY, chat_id)

    def add_chat_id(self, chat_id: int) -> bool:
        try:
            added = self.client.sadd("chat_ids", chat_id)
            logger.info(f"Chat ID {chat_id} {'added' if added else 'already exists'} in Redis.")
            return bool(added)
        except Exception as e:
            logger.error(f"Error adding chat_id to Redis: {e}")
            return False

    def get_all_chat_ids(self) -> list[int]:
        try:
            ids = self.client.smembers("chat_ids")
            return [int(cid) for cid in ids]
        except Exception as e:
            logger.error(f"Error retrieving chat_ids from Redis: {e}")
            return []

    def publish_broadcast(self, content_type: str, payload: dict) -> bool:
        """
        Publish a broadcast message to all listeners.

        :param content_type: 'text', 'photo', 'audio', etc.
        :param payload: A dict that includes all necessary fields (like 'text', 'file_id', 'caption')
        """
        try:
            message = json.dumps({
                "type": "broadcast",
                "content_type": content_type,
                **payload
            })
            self.client.publish(self.BROADCAST_CHANNEL, message)
            logger.info("Published broadcast to Redis.")
            return True
        except Exception as e:
            logger.error(f"Failed to publish broadcast: {e}")
            return False

    async def subscribe_to_broadcasts(self) -> AsyncGenerator[dict, None]:
        """
        Async generator that yields broadcast messages as dicts.
        Usage: `async for msg in redis_helper.subscribe_to_broadcasts(): ...`
        """
        try:
            pubsub = self.client.pubsub()
            pubsub.subscribe(self.BROADCAST_CHANNEL)

            logger.info("Subscribed to Redis broadcast channel.")

            while True:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
                if message and message["type"] == "message":
                    try:
                        yield json.loads(message["data"])
                    except Exception as parse_error:
                        logger.warning(f"Failed to parse broadcast JSON: {parse_error}")
                await asyncio.sleep(0.25)
        except Exception as e:
            logger.error(f"Redis subscription error: {e}")
            return
