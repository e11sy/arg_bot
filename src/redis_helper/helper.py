import redis
import logging
import json
from typing import AsyncGenerator
import asyncio
from telegram import Message

logger = logging.getLogger(__name__)

class RedisHelper:
    BROADCAST_CHANNEL = "broadcasts"
    AUTHORIZED_CHATS_KEY = "authorized_chats"
    METRICS_KEY_PREFIX = "metrics"

    def __init__(self, redis_url: str = None):
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

    def publish_raw_dict(self, message_dict: dict) -> bool:
        try:
            self.client.publish(self.BROADCAST_CHANNEL, json.dumps({
                "content_type": "message_dict",
                "message": message_dict
            }))
            return True
        except Exception as e:
            logger.error(f"Failed to publish raw message dict: {e}")
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
        
    def get_all_metrics(self) -> list[dict]:
        """
        Method that returns list of metrics for each chat that participates in the competition.
        Each element of the list contains list of metrics for each chat.
        """
        try:
            keys = self.client.keys(f"{self.METRICS_KEY_PREFIX}:*")
            metrics_list = []

            for key in keys:
                data = self.client.hgetall(key)
                if not data:
                    continue

                if "count" in data:
                    try:
                        data["count"] = int(data["count"])
                    except ValueError:
                        data["count"] = 0

                chat_id_str = key.split(":")[1]
                try:
                    data["chat_id"] = int(chat_id_str)
                except ValueError:
                    data["chat_id"] = chat_id_str

                metrics_list.append(data)

            return metrics_list

        except Exception as e:
            logger.error(f"Error retrieving metrics from Redis: {e}")
            return []
        
    def save_or_increment_metric(self, chat: dict) -> None:
        """
        Save the metrics for the chat or increment the counter of the existing one (atomically with Lua).
        """
        chat_id = chat["id"]
        key = f"{self.METRICS_KEY_PREFIX}:{chat_id}"

        fields = {
            "id": chat["id"],
            "type": chat.get("type"),
            "title": chat.get("title"),
            "username": chat.get("username"),
            "invite_link": chat.get("invite_link"),
        }
        
        # remove None values and convert to str
        fields = {k: str(v) for k, v in fields.items() if v is not None}

        # Lua-script: if key exists -> HINCRBY count
        # else -> HSET all fields + count=1
        lua_script = """
        if redis.call("EXISTS", KEYS[1]) == 1 then
            redis.call("HINCRBY", KEYS[1], "count", 1)
            for i=1, n-1, 2 do
              if args[i] == "invite_link" then
                redis.call("HSET", KEYS[1], args[i], ARGV[1 + 1])
            end
        else
            local args = ARGV
            local n = #args
            for i=1, n-1, 2 do
                redis.call("HSET", KEYS[1], args[i], args[i+1])
            end
            redis.call("HSET", KEYS[1], "count", 1)
            return 1
        end
        """

        args = []
        for k, v in fields.items():
            args.extend([k, v])

        script = self.client.register_script(lua_script)
        script(keys=[key], args=args)