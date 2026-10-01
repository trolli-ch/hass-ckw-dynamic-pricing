"""Config flow for CKW Dynamic Pricing integration."""
from typing import Any, Dict, Optional

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

DOMAIN = "ckw_dynamic_pricing"


class CKWConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CKW Dynamic Pricing."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Create the single entry; there is nothing to configure."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="CKW Dynamic Pricing", data={})
