from pydantic_settings import BaseSettings
from dotenv import find_dotenv
from functools import lru_cache


class Config(BaseSettings):
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_BOT_USERNAME: str = "meeting_assistant_bot"
    AGENT_API_URL: str
    HANDLE_MESSAGE_EDITS: bool = True
    EDIT_RESPONSE_TIMEOUT: int = 30
    AUTO_CONNECT_ON_START: bool = True

    class Config:
        env_file_encoding = "utf-8"
        extra = "allow"


@lru_cache()
def get_config(env_file: str = ".env") -> Config:
    return Config(_env_file=find_dotenv(env_file))


config: Config = get_config()
