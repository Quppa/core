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

CONF_SCAN_DEVICES = "scan_devices"

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
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

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
                vol.Required(
                    CONF_SCAN_DEVICES,
                    default=True,
                ): cv.boolean,
            }
        )

        if user_input is not None:
            scan_devices = user_input[CONF_SCAN_DEVICES]

            if scan_devices:
                devices = PowerpalHelper.find_devices()

                if len(devices) == 0:
                    errors["base"] = "no_devices"
                # elif len(devices) == 1:
                #    (device_address, device_name) = devices[0]
                #    return await self.async_setup(
                #        device_address=device_address, device_name=device_name
                #    )
                else:
                    return await self.async_select_device(devices=devices)
            else:
                return await self.async_setup()

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
        )

    async def async_select_device(
        self, user_input=None, devices: list[(str, str)] = []
    ):
        """TODO"""

        _LOGGER.info(f"async_select_device: {user_input}, devices: {devices}")

        data_schema = vol.Schema(
            {
                vol.Required(CONF_MAC, default=DEFAULT_MAC): vol.In(devices),
            }
        )

        if user_input is not None:
            device: str = user_input[CONF_MAC]

            return await self.async_setup(device=device)

        return self.async_show_form(
            step_id="select_device",
            data_schema=data_schema,
        )

    async def async_setup(
        self, user_input=None, device_address: str = None, device_name: str = None
    ):
        """TODO"""

        _LOGGER.info(
            f"async_setup: {user_input}, device_address: {device_address}, device_name: {device_name}"
        )

        errors = {}

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if self.hass.data.get(DOMAIN):
            return self.async_abort(reason="single_instance_allowed")

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_MAC, default=(device_address or DEFAULT_MAC)
                ): cv.string,
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
                valid = PowerpalHelper.validate_device(mac)

                if not valid:
                    errors[CONF_MAC] = "invalid_device"

                return True
                # self.powerpal_helper = PowerpalHelper(
                # mac, pairing_code, impulse_rate
                # )

                try:
                    await self.powerpal_helper.set_up()

                    # return self.async_create_entry(
                    #     title=self.collector.locations_data["data"]["name"],
                    #     data=self.data,
                    # )
                except Exception as e:
                    _LOGGER.exception(e)

        # If there is no user input or there were errors, show the form again, including any errors that were found with the input.
        return self.async_show_form(
            step_id="setup",
            data_schema=data_schema,
            errors=errors,
        )
