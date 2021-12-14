"""Config flow to configure the Latticework AmberOS integration."""
from __future__ import annotations

from ipaddress import ip_address
import logging
from typing import Any

import voluptuous as vol

from homeassistant import exceptions
from homeassistant.components import ssdp
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import (
    CONF_HOST,
    CONF_MAC,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SSL,
    CONF_TIMEOUT,
    CONF_USERNAME
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import DiscoveryInfoType

from latticework_amberos.latticework_amberos import LatticeworkAmberOS

from .const import (
    CONF_DEVICE_TOKEN,
    CONF_MODEL,
    CONF_VERSION,
    DEFAULT_PORT,
    DEFAULT_PORT_SSL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DEFAULT_USE_SSL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

def _discovery_schema_with_defaults(discovery_info: DiscoveryInfoType) -> vol.Schema:
    return vol.Schema(_ordered_shared_schema(discovery_info))


def _reauth_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
        }
    )


def _user_schema_with_defaults(user_input: dict[str, Any]) -> vol.Schema:
    user_schema = {
        vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, "")): str,
    }
    user_schema.update(_ordered_shared_schema(user_input))

    return vol.Schema(user_schema)


def _ordered_shared_schema(
    schema_input: dict[str, Any]
) -> dict[vol.Required | vol.Optional, Any]:
    return {
        vol.Required(CONF_USERNAME, default=schema_input.get(CONF_USERNAME, "")): str,
        vol.Required(CONF_PASSWORD, default=schema_input.get(CONF_PASSWORD, "")): str,
        vol.Optional(CONF_PORT, default=schema_input.get(CONF_PORT, "")): str,
        vol.Optional(
            CONF_SSL, default=schema_input.get(CONF_SSL, DEFAULT_USE_SSL)
        ): bool,
    }


def _is_valid_ip(text: str) -> bool:
    try:
        ip_address(text)
    except ValueError:
        return False
    return True


class LatticeworkAmberOSFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> LatticeworkAmberOSOptionsFlowHandler:
        """Get the options flow for this handler."""
        return LatticeworkAmberOSOptionsFlowHandler(config_entry)

    def __init__(self) -> None:
        """Initialize the latticework_amberos config flow."""
        self.saved_user_input: dict[str, Any] = {}
        self.discovered_conf: dict[str, Any] = {}
        self.reauth_conf: dict[str, Any] = {}
        self.reauth_reason: str | None = None

    def _show_form(
        self,
        step_id: str,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, str] | None = None,
    ) -> FlowResult:
        """Show the setup form to the user."""
        if not user_input:
            user_input = {}

        description_placeholders = {}
        data_schema = {}

        if step_id == "login":
            user_input.update(self.discovered_conf)
            data_schema = _discovery_schema_with_defaults(user_input)
            description_placeholders = self.discovered_conf
        elif step_id == "reauth_confirm":
            data_schema = _reauth_schema()
        elif step_id == "user":
            data_schema = _user_schema_with_defaults(user_input)

        return self.async_show_form(
            step_id=step_id,
            data_schema=data_schema,
            errors=errors or {},
            description_placeholders=description_placeholders,
        )

    async def async_validate_input_create_entry(
        self, user_input: dict[str, Any], step_id: str
    ) -> FlowResult:
        """Process user input and create new or update existing config entry."""
        host = user_input[CONF_HOST]
        port = user_input.get(CONF_PORT)
        username = user_input[CONF_USERNAME]
        password = user_input[CONF_PASSWORD]
        use_ssl = user_input.get(CONF_SSL, DEFAULT_USE_SSL)

        if not port:
            if use_ssl is True:
                port = DEFAULT_PORT_SSL
            else:
                port = DEFAULT_PORT

        api = LatticeworkAmberOS(
            host, port, username, password, use_ssl, timeout=30
        )

        errors = {}
        try:
            serial = await self.hass.async_add_executor_job(
                _login_and_fetch_info, api
            )
        except InvalidData:
            errors["base"] = "missing_data"

        if errors:
            return self._show_form(step_id, user_input, errors)

        # unique_id should be serial for services purpose
        existing_entry = await self.async_set_unique_id(serial, raise_on_progress=False)

        config_data = {
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_SSL: use_ssl,
            CONF_USERNAME: username,
            CONF_PASSWORD: password,
            CONF_MAC: api.network.macs,
            CONF_NAME: api.network.hostname
        }
        config_data[CONF_DEVICE_TOKEN] = api.device_token

        if existing_entry:
            self.hass.config_entries.async_update_entry(
                existing_entry, data=config_data
            )
            await self.hass.config_entries.async_reload(existing_entry.entry_id)
            if self.reauth_conf:
                return self.async_abort(reason="reauth_successful")
            return self.async_abort(reason="reconfigure_successful")
        config_title = "{} ({})".format(api.network.hostname, host)
        return self.async_create_entry(title=config_title, data=config_data)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initiated by the user."""
        step = "user"
        if not user_input:
            return self._show_form(step)
        return await self.async_validate_input_create_entry(user_input, step_id=step)

    async def async_step_zeroconf(self, discovery_info: DiscoveryInfoType) -> FlowResult:
        """Handle a discovered latticework amberos."""

        host = discovery_info.properties.get("ip")
        if not _is_valid_ip(host):
            raise InvalidData

        friendly_name = discovery_info.properties.get("hostname", "unknown")
        discovered_mac = discovery_info.properties.get("macaddr").upper()
        model = discovery_info.properties.get(CONF_MODEL, "unknown")
        version = discovery_info.properties.get(CONF_VERSION, "unknown")
        await self.async_set_unique_id(discovered_mac)
        existing_entry = self._async_get_existing_entry(discovered_mac)

        if not existing_entry:
            self._abort_if_unique_id_configured()

        if existing_entry:
            return self.async_abort(reason="already_configured")

        self.discovered_conf = {
            CONF_NAME: friendly_name,
            CONF_HOST: host,
            CONF_MODEL: model,
            CONF_VERSION: version
        }
        self.context["title_placeholders"] = self.discovered_conf
        return await self.async_step_login()

    async def async_step_login(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Login a config entry from discovery."""
        step = "login"
        if not user_input:
            return self._show_form(step)
        user_input = {**self.discovered_conf, **user_input}
        return await self.async_validate_input_create_entry(user_input, step_id=step)

    async def async_step_reauth(self, data: dict[str, Any]) -> FlowResult:
        """Perform reauth upon an API authentication error."""
        self.reauth_conf = data.copy()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Perform reauth confirm upon an API authentication error."""
        step = "reauth_confirm"
        if not user_input:
            return self._show_form(step)
        user_input = {**self.reauth_conf, **user_input}
        return await self.async_validate_input_create_entry(user_input, step_id=step)

    def _async_get_existing_entry(self, discovered_mac: str) -> ConfigEntry | None:
        """See if we already have a configured NAS with this MAC address."""
        for entry in self._async_current_entries():
            if discovered_mac in [
                mac.replace("-", "") for mac in entry.data.get(CONF_MAC, [])
            ]:
                return entry
        return None


class LatticeworkAmberOSOptionsFlowHandler(OptionsFlow):
    """Handle a option flow."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): cv.positive_int,
                vol.Optional(
                    CONF_TIMEOUT,
                    default=self.config_entry.options.get(
                        CONF_TIMEOUT, DEFAULT_TIMEOUT
                    ),
                ): cv.positive_int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)


def _login_and_fetch_info(api: LatticeworkAmberOS) -> str:
    """Login to the NAS and fetch basic data."""
    # These do i/o
    api.login()
    api.information.update()
    api.system.update()
    api.utilisation.update()
    api.storage.update()
    api.network.update()

    if (
        not api.information.serial
        or api.utilisation.cpu_user_load is None
        or not api.storage.volumes_ids
        or not api.network.macs
    ):
        raise InvalidData

    return api.information.serial  # type: ignore[no-any-return]

class InvalidData(exceptions.HomeAssistantError):
    """Error to indicate we get invalid data from the nas."""
