"""Support for AmberOS Cast select entities."""
from __future__ import annotations


from homeassistant import config_entries
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import (
    ENTITY_CATEGORY_CONFIG
)
from homeassistant.core import HomeAssistant

from . import AmberOSApi
from latticework_amberos.api.amberos_cast_api import AmberOSCast
from .const import (
    AMBEROS_API,
    ATTR_MANUFACTURER,
    DOMAIN,
    FEATURE_CAST_SELECTOR,
    SELECTOR_TYPES
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select(s) for AmberOS cast."""

    data = hass.data[DOMAIN][entry.unique_id]
    api: AmberOSApi = data[AMBEROS_API]

    unique_id = entry.unique_id
    default_name = f"{api.network.hostname} Cast Source Select"

    assert unique_id is not None
    device_info = DeviceInfo(
        identifiers={(DOMAIN, api.information.serial)},
        manufacturer=ATTR_MANUFACTURER,
        model=api.information.model,
        sw_version=api.information.version_string,
        name="Latticework AmberOS",
        via_device=(DOMAIN, api.information.serial),
        configuration_url=api.config_url,
    )

    description = SELECTOR_TYPES[FEATURE_CAST_SELECTOR]
    async_add_entities(
        [AmberOSCastSelect(api, default_name, unique_id, device_info, description)]
    )


class AmberOSCastSelect(SelectEntity):
    """Representation of a AmberOS Cast source select."""

    _device: str

    def __init__(
        self,
        api,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
        description
    ) -> None:
        self._attr_current_option = None
        self._attr_options: list | None = []
        self._attr_device_info = device_info
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._api = api
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return bool(self._api.cast)

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        self._attr_options = self._api.cast.source_list

    async def after_update_callback(self, device: str) -> None:
        """Call after device was updated."""
        self._attr_current_option = self.api.cast.source

        await super().after_update_callback(device)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self._api.cast.async_select_source(option)
