"""Local repair workspace. No network, telemetry or payment processing."""
from .repository import ServiceStore
from .validation import ServiceError

__all__ = ['ServiceStore', 'ServiceError']
