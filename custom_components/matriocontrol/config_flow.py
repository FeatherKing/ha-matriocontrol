"""Config flow for Matrio Control integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import DEFAULT_PORT, DEFAULT_ZONES, DOMAIN
from .dax88_controller import DAX88Controller

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional("zones", default=DEFAULT_ZONES): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=8)
        ),
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Matrio Control."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            # Test connection
            controller = DAX88Controller(
                user_input[CONF_HOST], user_input[CONF_PORT]
            )
            await self.hass.async_add_executor_job(controller.connect)
            await self.hass.async_add_executor_job(controller.disconnect)
        except Exception as ex:
            _LOGGER.error("Failed to connect to DAX88: %s", ex)
            errors["base"] = "cannot_connect"

        if not errors:
            return self.async_create_entry(
                title=f"DAX88 ({user_input[CONF_HOST]})", data=user_input
            )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )