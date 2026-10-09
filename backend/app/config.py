from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RVM_", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/tasmac_rvm"
    db_echo: bool = False

    # Refund rules
    refund_amount_paise: int = 1000
    reservation_ttl_s: int = 600          # refund QR reserved for a session this long

    # QR verification (test format until TASMAC shares the real one)
    qr_signing_secret: str = "tasmac-test-secret-change-me"
    # Accept real bottle QRs that an operator registered in the admin portal (demo / pilot).
    # Turn off once TASMAC's own verification is integrated.
    qr_registry_enabled: bool = True

    # Providers: "mock" until real accounts exist
    payout_provider: str = "mock"
    sms_provider: str = "mock"            # mock | android_gateway (internal testing only)
    # "SMS Gateway for Android" app in Local Server mode (sms-gate.app): a test phone sends the SMS
    # from its own SIM. Testing only - production SMS needs DLT + a registered provider.
    sms_gateway_url: str = ""              # e.g. http://192.168.1.3:8080
    sms_gateway_username: str = ""
    sms_gateway_password: str = ""
    sms_gateway_timeout_s: float = 10.0
    payout_webhook_secret: str = "change-me"

    # Reconciler: polls PENDING payouts in the background
    reconcile_interval_s: float = 15.0
    reconcile_after_s: float = 10.0

    # Admin login (JWT). Set a long random RVM_JWT_SECRET in production.
    jwt_secret: str = "dev-only-change-me-0123456789abcdef"
    jwt_ttl_minutes: int = 480
    login_max_failures: int = 5
    login_lockout_minutes: int = 15

    # Alerts
    machine_offline_after_s: int = 120
    bin_full_alert_pct: int = 85
    payout_stuck_after_s: int = 600

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:5174"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
