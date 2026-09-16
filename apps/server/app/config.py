# -*- coding: utf-8 -*-
from __future__ import annotations
from functools import lru_cache
from typing import Literal
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env", "../../.env"), env_file_encoding="utf-8", case_sensitive=False, extra="ignore")
    app_name: str = Field(default="AxiomForge-Engine", alias="axiom_app_name")
    env: Literal["development", "staging", "production"] = Field(default="development", alias="axiom_env")
    debug: bool = Field(default=False, alias="axiom_debug")
    api_url: str = Field(default="http://localhost:8000", alias="axiom_api_url")
    ws_url: str = Field(default="ws://localhost:8000", alias="axiom_ws_url")
    frontend_port: int = Field(default=3000, alias="axiom_frontend_port")
    frontend_host: str = Field(default="0.0.0.0", alias="axiom_frontend_host")
    auth_secret: str = Field(default="change-me", alias="axiom_auth_secret")
    session_secret: str = Field(default="change-me", alias="axiom_session_secret")
    backend_host: str = Field(default="0.0.0.0", alias="axiom_backend_host")
    backend_port: int = Field(default=8000, alias="axiom_backend_port")
    backend_reload: bool = Field(default=True, alias="axiom_backend_reload")
    cors_origins: str = Field(default='["http://localhost:3000"]', alias="axiom_cors_origins")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="axiom_redis_url")
    redis_cache_url: str = Field(default="redis://localhost:6379/1", alias="axiom_redis_cache_url")
    celery_always_eager: bool = Field(default=False, alias="axiom_celery_task_always_eager")
    celery_task_time_limit: int = Field(default=600, alias="axiom_celery_task_time_limit")
    celery_worker_concurrency: int = Field(default=2, alias="axiom_celery_worker_concurrency")
    celery_flower_enabled: bool = Field(default=True, alias="axiom_celery_flower_enabled")
    celery_flower_port: int = Field(default=5555, alias="axiom_celery_flower_port")
    pg_user: str = Field(default="axiom", alias="axiom_pg_user")
    pg_password: str = Field(default="change-me", alias="axiom_pg_password")
    pg_db: str = Field(default="axiom", alias="axiom_pg_db")
    pg_host: str = Field(default="localhost", alias="axiom_pg_host")
    pg_port: int = Field(default=5432, alias="axiom_pg_port")
    pg_vector_dim: int = Field(default=1536, alias="axiom_pg_vector_dim")
    sqlalchemy_url: str = Field(default="", alias="axiom_sqlalchemy_url")
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="axiom_neo4j_uri")
    neo4j_user: str = Field(default="neo4j", alias="axiom_neo4j_user")
    neo4j_password: str = Field(default="change-me", alias="axiom_neo4j_password")
    neo4j_db: str = Field(default="neo4j", alias="axiom_neo4j_db")
    weaviate_url: str = Field(default="http://localhost:8080", alias="axiom_weaviate_url")
    weaviate_api_key: str = Field(default="change-me", alias="axiom_weaviate_api_key")
    weaviate_infra_url: str = Field(default="http://localhost:8080", alias="axiom_weaviate_infra_url")
    llm_provider: str = Field(default="openai", alias="axiom_llm_provider")
    llm_base_url: str = Field(default="https://api.openai.com/v1", alias="axiom_llm_base_url")
    llm_api_key: str = Field(default="change-me", alias="axiom_llm_api_key")
    llm_model: str = Field(default="gpt-4o-mini", alias="axiom_llm_model")
    embedding_model: str = Field(default="text-embedding-3-small", alias="axiom_llm_embedding_model")
    embedding_dim: int = Field(default=1536, alias="axiom_llm_embedding_dim")
    langchain_tracing: bool = Field(default=False, alias="axiom_langchain_tracing")
    langchain_api_key: str = Field(default="", alias="axiom_langchain_api_key")
    langchain_project: str = Field(default="AxiomForge-Engine", alias="axiom_langchain_project")
    log_level: str = Field(default="info", alias="axiom_log_level")
    max_file_upload_mb: int = Field(default=50, alias="axiom_max_file_upload_mb")
    default_locale: str = Field(default="en", alias="axiom_default_locale")
    default_sandbox_turns: int = Field(default=20, alias="axiom_default_sandbox_turns")
    telemetry: bool = Field(default=False, alias="axiom_telemetry")

    @property
    def pg_url(self) -> str:
        if self.sqlalchemy_url and self.sqlalchemy_url.startswith("postgresql"):
            return self.sqlalchemy_url
        pw = self.pg_password if self.pg_password else ""
        return f"postgresql+psycopg2://{self.pg_user}:{pw}@{self.pg_host}:{self.pg_port}/{self.pg_db}"

    @property
    def pg_sync_url(self) -> str:
        pw = self.pg_password if self.pg_password else ""
        return f"postgresql+psycopg2://{self.pg_user}:{pw}@{self.pg_host}:{self.pg_port}/{self.pg_db}"

    @model_validator(mode="after")
    def _ensure_secrets_not_empty_in_prod(self) -> Settings:
        if self.env == "production":
            for name, val in [
                ("AXIOM_AUTH_SECRET", self.auth_secret),
                ("AXIOM_PG_PASSWORD", self.pg_password),
                ("AXIOM_NEO4J_PASSWORD", self.neo4j_password),
                ("AXIOM_WEAVIATE_API_KEY", self.weaviate_api_key),
                ("AXIOM_LLM_API_KEY", self.llm_api_key),
            ]:
                if not val or str(val).startswith("change-me"):
                    raise ValueError(f"{name} must be set in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
