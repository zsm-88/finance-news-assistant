from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "ai-finance-wechat-assistant"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://finance:finance@localhost:5432/finance"
    redis_url: str = "redis://localhost:6379/0"
    admin_token: str | None = None
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model: str | None = None
    ai_assistant_cache_ttl_seconds: int = 60
    ai_assistant_max_events: int = 10
    ai_assistant_max_conversation_messages: int = 5
    ai_assistant_max_output_tokens: int = 900
    wecom_webhook_url: str | None = None
    collect_interval_seconds: int = 60
    max_task_retries: int = 3
    push_min_importance: int = 4
    timezone: str = "Asia/Shanghai"
    enable_crawler: bool = False
    enable_ai: bool = False
    enable_push: bool = False
    notification_merge_window_minutes: int = 15
    news_source_name: str = "cnbc"
    news_source_url: str = "https://www.cnbc.com/id/100003114/device/rss/rss.html"
    enable_chinanews: bool = True
    chinanews_rss_url: str = "https://www.chinanews.com.cn/rss/finance.xml"
    enable_tmtpost: bool = False
    tmtpost_rss_url: str = "https://www.tmtpost.com/rss.xml"
    enable_eastmoney: bool = True
    eastmoney_rss_url: str = "https://rss.eastmoney.com/rss/finance.xml"
    enable_cls: bool = True
    cls_rss_url: str = "https://www.cls.cn/telegraph"
    enable_stcn: bool = True
    stcn_rss_url: str = "https://www.stcn.com/rss/finance.xml"
    enable_wallstreetcn: bool = True
    wallstreetcn_rss_url: str = "https://wallstreetcn.com/rss/global"
    rss_request_timeout_seconds: int = 20
    enable_jin10: bool = False
    enable_cnbc_fallback: bool = True
    jin10_secret_key: str | None = None
    jin10_base_url: str = "https://open-data-api.jin10.com/data-api"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    jin10_market_category: int = 1
    jin10_request_timeout_seconds: int = 15
    max_items_per_cycle: int = 3
    notification_user_id: str = "00000000-0000-0000-0000-000000000001"
    push_destination: str = "personal-wecom"
    quiet_hours_start: str = "22:30"
    quiet_hours_end: str = "07:30"
    market_data_source_url: str = "https://query1.finance.yahoo.com"
    market_cache_ttl_seconds: int = 60
    market_request_timeout_seconds: int = 5
    market_history_cache_ttl_seconds: int = 900
    tushare_token: str | None = None
    tushare_base_url: str = "https://api.tushare.pro"
    fund_request_timeout_seconds: int = 15
    fund_user_id: str = "00000000-0000-0000-0000-000000000001"
    enable_experimental_fund_valuation: bool = False
    enable_experimental_sina_fund_valuation: bool = False
    enable_experimental_eastmoney_fund_data: bool = False
    fund_valuation_base_url: str = "https://fundcomapi.tiantianfunds.com"
    sina_fund_valuation_base_url: str = (
        "https://stock.finance.sina.com.cn/fundInfo/api/openapi.php"
    )
    eastmoney_fund_trend_base_url: str = "https://fund.eastmoney.com/pingzhongdata"
    eastmoney_fund_mobile_base_url: str = "https://fundmobapi.eastmoney.com"
    fund_valuation_request_timeout_seconds: int = 15
    fund_valuation_cache_ttl_seconds: int = 20
    fund_valuation_stale_seconds: int = 600
    fund_catalog_cache_ttl_seconds: int = 21600
    fund_nav_cache_ttl_seconds: int = 1800
    fund_nav_history_cache_ttl_seconds: int = 1800
    fund_holdings_cache_ttl_seconds: int = 21600
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
