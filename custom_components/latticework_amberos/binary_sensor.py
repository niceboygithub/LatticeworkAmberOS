"""Support for Latticework AmberOS binary sensors."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import  ATTR_ATTRIBUTION, CONF_DISKS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import AmberOSApi, LwAmberOSBaseEntity, LwAmberOSDeviceEntity
from .const import (
    ATTRIBUTION,
    COORDINATOR_CENTRAL,
    DOMAIN,
    BACKUP_BINARY_SENSORS,
    SECURITY_BINARY_SENSORS,
    STORAGE_DISK_BINARY_SENSORS,
    AMBEROS_API,
    UPGRADE_BINARY_SENSORS,
    AmberOSBinarySensorEntityDescription,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Latticework AmberOS binary sensor."""

    data = hass.data[DOMAIN][entry.unique_id]
    api: AmberOSApi = data[AMBEROS_API]
    coordinator = data[COORDINATOR_CENTRAL]

    entities: list[
        AmberOSSecurityBinarySensor
        | AmberOSUpgradeBinarySensor
        | AmberOSStorageBinarySensor
    ] = [
        AmberOSSecurityBinarySensor(api, coordinator, description)
        for description in SECURITY_BINARY_SENSORS
    ]

    entities.extend(
        [
            AmberOSBackupBinarySensor(api, coordinator, description)
            for description in BACKUP_BINARY_SENSORS
        ]
    )

    entities.extend(
        [
            AmberOSUpgradeBinarySensor(api, coordinator, description)
            for description in UPGRADE_BINARY_SENSORS
        ]
    )

    # Handle all disks
    if api.storage.disks_ids:
        entities.extend(
            [
                AmberOSStorageBinarySensor(api, coordinator, description, disk)
                for disk in entry.data.get(CONF_DISKS, api.storage.disks_ids)
                for description in STORAGE_DISK_BINARY_SENSORS
            ]
        )

    async_add_entities(entities)


class AmberOSBinarySensor(LwAmberOSBaseEntity, BinarySensorEntity):
    """Mixing for binary sensor specific attributes."""

    entity_description: AmberOSBinarySensorEntityDescription

    def __init__(
        self,
        api: AmberOSApi,
        coordinator: DataUpdateCoordinator[dict[str, dict[str, Any]]],
        description: AmberOSBinarySensorEntityDescription,
    ) -> None:
        """Initialize the Latticework AmberOS binary_sensor entity."""
        self._attr_extra_state_attributes = {ATTR_ATTRIBUTION: ATTRIBUTION}
        super().__init__(api, coordinator, description)


class AmberOSSecurityBinarySensor(AmberOSBinarySensor):
    """Representation a Latticework AmberOS Security binary sensor."""

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return getattr(self._api.security, self.entity_description.key) != "safe"  # type: ignore[no-any-return]

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return bool(self._api.security)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return security checks details."""
        attr = self._attr_extra_state_attributes
        attr.update(self._api.security.status_by_check)
        return attr


class AmberOSBackupBinarySensor(AmberOSBinarySensor):
    """Representation a Latticework AmberOS Backup binary sensor."""

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return getattr(self._api.backup, self.entity_description.key) == "running"  # type: ignore[no-any-return]

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return bool(self._api.backup)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return backup checks details."""
        attr = self._attr_extra_state_attributes
        attr.update(self._api.backup.status_by_check)
        return attr


class AmberOSStorageBinarySensor(LwAmberOSDeviceEntity, AmberOSBinarySensor):
    """Representation a Latticework AmberOS Storage binary sensor."""

    entity_description: AmberOSBinarySensorEntityDescription

    def __init__(
        self,
        api: AmberOSApi,
        coordinator: DataUpdateCoordinator[dict[str, dict[str, Any]]],
        description: AmberOSBinarySensorEntityDescription,
        device_id: str | None = None,
    ) -> None:
        """Initialize the Latticework AmberOS storage binary_sensor entity."""
        super().__init__(api, coordinator, description, device_id)

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return bool(
            getattr(self._api.storage, self.entity_description.key)(self._device_id)
        )


class AmberOSUpgradeBinarySensor(AmberOSBinarySensor):
    """Representation a Latticework AmberOS Upgrade binary sensor."""

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return bool(getattr(self._api.upgrade, self.entity_description.key))

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return bool(self._api.upgrade) and bool(self._api.information)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return firmware details."""
        attr = self._attr_extra_state_attributes
        if len(self._api.upgrade.available_version) >= 1:
            attr.update({
                "newest_version": self._api.upgrade.available_version,
                "release_notes": self._api.upgrade.release_notes,
            })
        attr.update({
            "installed_version": self._api.information.version_string,
        })
        return attr
