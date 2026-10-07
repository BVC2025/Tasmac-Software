"""Machine configuration, loaded from YAML."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class PLCConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 502
    device_id: int = 1
    lanes: int = Field(default=3, ge=1, le=3)   # bottle inlets on this machine
    write_base: int = 0
    read_base: int = 100
    poll_interval_s: float = 0.1
    heartbeat_interval_s: float = 0.5
    plc_heartbeat_timeout_s: float = 3.0
    connect_timeout_s: float = 3.0
    default_cmd_timeout_s: float = 10.0
    cmd_timeouts_s: dict[str, float] = Field(default_factory=dict)


class SimulatorConfig(BaseModel):
    enabled: bool = False
    time_scale: float = 1.0           # <1 makes simulated motion faster
    auto_insert_every_s: float | None = None
    bottles_file: str | None = None   # Test bottle feed (YAML)
    fresh_qr_on_start: bool = True    # new QR serials every start (backend rejects reused QRs)


class FlowConfig(BaseModel):
    batch_window_s: float = 3.0        # after the first bottle, wait this long for bottles in other inlets
    inspection_angles: int = 4         # Images per bottle (rotating between)
    qr_scan_max_rotations: int = 8
    close_inlet_retries: int = 3
    customer_input_timeout_s: float = 60.0
    max_destination_attempts: int = 3
    payout_poll_interval_s: float = 2.0
    payout_pending_wait_s: float = 30.0
    on_payout_pending_timeout: Literal["accept", "return"] = "accept"
    fault_retry_interval_s: float = 2.0
    hand_retry_interval_s: float = 1.0
    backend_check_interval_s: float = 5.0
    backend_failures_before_oos: int = 2   # consecutive failed health checks


class QRConfig(BaseModel):
    # Test-only secret: real QR format/keys come from TASMAC.
    test_signing_secret: str = "tasmac-test-secret-change-me"


class BackendConfig(BaseModel):
    url: str = "http://127.0.0.1:8000"
    api_key: str = ""
    timeout_s: float = 8.0
    outbox_path: str = "data/outbox.db"
    heartbeat_interval_s: float = 15.0


class LocalApiConfig(BaseModel):
    """Local API for the kiosk touchscreen UI."""
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8765
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


class CameraConfig(BaseModel):
    """Real cameras (vision_driver: camera). Lane -> OpenCV device index or stream URL.

    DroidCam / Iriun on a PC: the phone appears as a webcam (index 0, 1, ...), or use
    the DroidCam Wi-Fi stream directly: "http://<phone-ip>:4747/video".
    Lanes without an entry share the first camera.
    """
    sources: dict[int, int | str] = Field(default_factory=lambda: {1: 0})
    width: int = 1280
    height: int = 720
    frame_interval_s: float = 0.35   # pause before each capture so the bottle can turn
    backend: Literal["auto", "dshow", "msmf"] = "auto"


class MachineConfig(BaseModel):
    machine_id: str = "RVM-DEV-001"
    software_version: str = "0.3.0"
    session_log_path: str | None = "data/sessions.db"   # local audit trail (SQLite)
    plc: PLCConfig = Field(default_factory=PLCConfig)
    simulator: SimulatorConfig = Field(default_factory=SimulatorConfig)
    flow: FlowConfig = Field(default_factory=FlowConfig)
    qr: QRConfig = Field(default_factory=QRConfig)
    backend: BackendConfig = Field(default_factory=BackendConfig)
    local_api: LocalApiConfig = Field(default_factory=LocalApiConfig)
    camera: CameraConfig = Field(default_factory=CameraConfig)
    vision_driver: Literal["mock", "camera"] = "mock"   # camera = real QR reading, inspection still simulated
    backend_driver: Literal["mock", "http"] = "mock"
    customer_driver: Literal["auto", "web"] = "auto"


def load_config(path: str | Path) -> MachineConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return MachineConfig.model_validate(data)
