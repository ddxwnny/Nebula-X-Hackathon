"""LTA DataMall adapters for station exits and station-specific lift outages.

Aliased to unified LTAClient in clients.lta_client for backward compatibility.
"""

from clients.lta_client import LTAClient as LtaDataMallClient

__all__ = ["LtaDataMallClient"]
