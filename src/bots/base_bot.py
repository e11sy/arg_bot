from abc import ABC, abstractmethod
from telegram.ext import Application
from redis_helper.helper import RedisHelper
import logging

class BaseBot(ABC):
    def __init__(self, logger: logging.Logger, redis_helper: RedisHelper):
        self.logger = logger
        self.redis = redis_helper

    @abstractmethod
    def register_handlers(self, app: Application) -> None:
        pass

    @abstractmethod
    async def handle_start(self, update, context) -> None:
        pass
