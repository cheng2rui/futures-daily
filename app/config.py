from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8500


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///./data/futures_daily.db"


class SchedulerConfig(BaseModel):
    enabled: bool = True
    timezone: str = "Asia/Shanghai"
    daily_report_cron: str = "20 16 * * 1-5"


class ExchangeConfig(BaseModel):
    enabled: list[str] = Field(default_factory=lambda: ["DCE", "CZCE", "SHFE", "CFFEX", "GFEX", "INE"])


class ReportConfig(BaseModel):
    include_financial_futures: bool = True
    include_commodity_futures: bool = True
    include_seat_report: bool = True
    trading_day_mode: str = "auto"


class SeatArchiveConfig(BaseModel):
    enabled: bool = True
    path: str = "/rsstsx/structured_archive"
    summary_path: str = "/rsstsx"


class NotifyChannelConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    webhook_url: str = ""
    msg_type: str = "text"
    token: str = ""
    claw_base_url: str = "https://ilinkai.weixin.qq.com"
    claw_target: str = ""


class NotifyConfig(BaseModel):
    telegram: NotifyChannelConfig = Field(default_factory=NotifyChannelConfig)
    wecom: NotifyChannelConfig = Field(default_factory=NotifyChannelConfig)
    wechatbot: NotifyChannelConfig = Field(default_factory=NotifyChannelConfig)


class AssistantProviderConfig(BaseModel):
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    temperature: float = 0.2


class AssistantFeaturesConfig(BaseModel):
    daily_summary: bool = False
    seat_analysis: bool = False
    symbol_explain: bool = False
    push_digest: bool = False


class AssistantConfig(BaseModel):
    enabled: bool = False
    global_chat: bool = False
    provider: AssistantProviderConfig = Field(default_factory=AssistantProviderConfig)
    features: AssistantFeaturesConfig = Field(default_factory=AssistantFeaturesConfig)


class Settings(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    exchanges: ExchangeConfig = Field(default_factory=ExchangeConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    seat_archive: SeatArchiveConfig = Field(default_factory=SeatArchiveConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    assistant: AssistantConfig = Field(default_factory=AssistantConfig)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    path = Path(os.getenv("FUTURES_DAILY_CONFIG", "config/config.yaml"))
    data = _read_yaml(path)
    db_override = os.getenv("FUTURES_DAILY_DB")
    if db_override:
        data.setdefault("database", {})["url"] = f"sqlite:///{db_override}"
    return Settings.model_validate(data)
