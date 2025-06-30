"""Pydantic models for solana-radar."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PumpEvent(BaseModel):
    """Represents a pump.fun token event."""

    # Token identifiers
    mint: str = Field(..., description="Token mint address")
    name: str = Field(..., description="Token name")
    symbol: str = Field(..., description="Token symbol")

    # Market data
    market_cap: float = Field(..., description="Current market cap in SOL")
    price: float = Field(..., description="Current token price")
    volume_24h: float = Field(0.0, description="24h trading volume")

    # Token metadata
    description: Optional[str] = Field(None, description="Token description")
    image_uri: Optional[str] = Field(None, description="Token image URI")
    metadata_uri: Optional[str] = Field(None, description="Token metadata URI")
    twitter: Optional[str] = Field(None, description="Twitter handle")
    telegram: Optional[str] = Field(None, description="Telegram link")
    website: Optional[str] = Field(None, description="Website URL")

    # Trading data
    bonding_curve: Optional[str] = Field(None, description="Bonding curve address")
    associated_bonding_curve: Optional[str] = Field(
        None, description="Associated bonding curve"
    )
    creator: Optional[str] = Field(None, description="Token creator address")

    # Event metadata
    event_type: str = Field("new_token", description="Type of event")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}
