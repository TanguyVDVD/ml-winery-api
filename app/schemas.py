from pydantic import BaseModel, Field


class PeltierMeasurement(BaseModel):
    """One row of the peltier table, as sent by the Pi once per minute.

    The bounds reject absurd values (or a caller that is not the Pi) with a 422.
    peltier_temp and fan_rpm may be missing: failed probe, tachometer not wired.
    """

    peltier_id: str = Field(max_length=50)
    is_on: bool
    peltier_temp: float | None = Field(default=None, ge=-40, le=125)
    ambient_temp: float = Field(ge=-40, le=125)
    fan_rpm: int | None = Field(default=None, ge=0, le=20_000)
