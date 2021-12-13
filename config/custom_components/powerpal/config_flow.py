"""Config flow for Powerpal."""

import logging
import re
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_MAC,
    CONF_ACCESS_TOKEN,
    CONF_COUNT,
)

import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    DEFAULT_MAC,
    DEFAULT_PAIRING_CODE,
    DEFAULT_IMPULSE_RATE,
    REGEX_MAC,
    REGEX_PAIRING_CODE,
)

from .sensor import PowerpalHelper

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Powerpal config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def validate_regex(self, value: str, regex: str):
        """Validate that the value is a string that matches a regex."""
        compiled = re.compile(regex)
        if not compiled.match(value):
            return False
        return True

    def validate_mac(self, value: str, errors: list):
        """Mac validation."""
        if not self.validate_regex(value, REGEX_MAC):
            errors[CONF_MAC] = "invalid_mac"

    def validate_pairing_code(self, value: str, errors: list):
        """Pairing code validation."""
        if not self.validate_regex(value, REGEX_PAIRING_CODE):
            errors[CONF_ACCESS_TOKEN] = "invalid_pairing_code"

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""

        _LOGGER.info(f"async_step_user: {user_input}")

        errors = {}

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if self.hass.data.get(DOMAIN):
            return self.async_abort(reason="single_instance_allowed")

        data_schema = vol.Schema(
            {
                vol.Required(CONF_MAC, default=DEFAULT_MAC): cv.string,
                vol.Required(
                    CONF_ACCESS_TOKEN, default=DEFAULT_PAIRING_CODE
                ): cv.string,
                vol.Required(CONF_COUNT, default=DEFAULT_IMPULSE_RATE): cv.positive_int,
            }
        )

        if user_input is not None:
            mac = user_input[CONF_MAC]
            pairing_code = user_input[CONF_ACCESS_TOKEN]
            impulse_rate = user_input[CONF_COUNT]

            self.validate_mac(mac, errors)
            self.validate_pairing_code(pairing_code, errors)

            if not errors:
                self.mac = mac
                self.pairing_code = int(pairing_code)
                self.impulse_rate = impulse_rate

                self.powerpal_helper = PowerpalHelper(
                    self.mac, self.pairing_code, self.impulse_rate
                )

                try:
                    await self.powerpal_helper.set_up()
                except Exception as e:
                    _LOGGER.exception(e)

        # If there is no user input or there were errors, show the form again, including any errors that were found with the input.
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
