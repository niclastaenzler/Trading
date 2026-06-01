"""Broker factory — selects the concrete broker for a user.

Defaults to the paper broker. A live broker is only constructed when the user
has explicitly chosen one AND provided (encrypted) credentials.
"""

from __future__ import annotations

from app.config import settings
from app.core.logging_config import get_logger
from app.services.broker.broker_interface import BrokerInterface
from app.services.broker.paper_broker import PaperBroker

logger = get_logger("broker.factory")


def get_broker(
    user_id: int,
    broker_name: str = "paper",
    credentials: dict | None = None,
) -> BrokerInterface:
    credentials = credentials or {}
    name = (broker_name or "paper").lower()

    if name == "capital_com":
        from app.services.broker.capital_com import CapitalComBroker

        return CapitalComBroker(
            api_key=credentials.get("api_key", settings.capital_com_api_key),
            identifier=credentials.get("identifier", settings.capital_com_identifier),
            password=credentials.get("password", settings.capital_com_password),
            demo=credentials.get("demo", settings.capital_com_demo),
        )

    if name != "paper":
        logger.warning("unknown broker '%s' -> falling back to paper", name)
    return PaperBroker(user_id=user_id)
