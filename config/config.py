from pydantic import SecretStr, model_validator, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    DEBUG: bool = False
    ALLOWED_HOSTS: list[str] = ['*']
    SECRET_KEY: SecretStr

    DB_ENGINE: str
    DB_NAME: str
    DB_USER: str | None = None
    DB_PASSWORD: SecretStr | None = None
    DB_HOST: str = 'localhost'
    DB_PORT: str = ''

    # Set to false only when the app is served over plain HTTP behind no TLS
    # terminator (e.g. LAN-only deployment); secure cookies would then never
    # be sent and login could not work.
    HTTPS: bool = True
    CSRF_TRUSTED_ORIGINS: list[str] = []

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )


env_config = Settings()
