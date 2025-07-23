from pydantic import SecretStr, model_validator, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    DEBUG: bool = False
    ALLOWED_HOSTS: list[str] = ['*']
    SECRET_KEY: SecretStr

    DB_ENGINE: str
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: SecretStr
    DB_HOST: str = 'localhost'
    DB_PORT: str = ''

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )


env_config = Settings()
