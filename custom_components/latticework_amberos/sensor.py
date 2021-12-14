"""Support for Latticework AmberOS sensors."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity
from homeassistant.util.dt import utcnow
from homeassistant.const import (
    CONF_DISKS,
    DATA_MEGABYTES,
    DATA_GIGABYTES,
    DATA_RATE_KILOBYTES_PER_SECOND,
    DATA_TERABYTES,
)

from . import AmberOSApi, LwAmberOSBaseEntity, LwAmberOSDeviceEntity
from .const import (
    AMBEROS_API,
    COORDINATOR_CENTRAL,
    CONF_VOLUMES,
    DOMAIN,
    ENTITY_UNIT_LOAD,
    INFORMATION_SENSORS,
    STORAGE_DISK_SENSORS,
    STORAGE_VOL_SENSORS,
    UTILISATION_SENSORS,
    AmberOSSensorEntityDescription,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Latticework AmberOS Sensor."""

    data = hass.data[DOMAIN][entry.unique_id]
    api: AmberOSApi = data[AMBEROS_API]
    coordinator = data[COORDINATOR_CENTRAL]

    try:
        entities: list[AmberOSUtilSensor | AmberOSStorageSensor | AmberOSInfoSensor] = [
            AmberOSUtilSensor(api, coordinator, description)
            for description in UTILISATION_SENSORS
        ]

        # Handle all volumes
        if api.storage.volumes_ids:
            entities.extend(
                [
                    AmberOSStorageSensor(api, coordinator, description, volume)
                    for volume in entry.data.get(CONF_VOLUMES, api.storage.volumes_ids)
                    for description in STORAGE_VOL_SENSORS
                ]
            )

        # Handle all disks
        if api.storage.disks_ids:
            entities.extend(
                [
                    AmberOSStorageSensor(api, coordinator, description, disk)
                    for disk in entry.data.get(CONF_DISKS, api.storage.disks_ids)
                    for description in STORAGE_DISK_SENSORS
                ]
            )

        entities.extend(
            [
                AmberOSInfoSensor(api, coordinator, description)
                for description in INFORMATION_SENSORS
            ]
        )

        async_add_entities(entities)
    except AttributeError as e:
        _LOGGER.error(e)

class AmberOSSensor(LwAmberOSBaseEntity, SensorEntity):
    """ for sensor specific attributes."""

    entity_description: AmberOSSensorEntityDescription

    def __init__(
        self,
        api: AmberOSApi,
        coordinator: DataUpdateCoordinator[dict[str, dict[str, Any]]],
        description: AmberOSSensorEntityDescription,
    ) -> None:
        """Initialize the AmberOS sensor entity."""
        super().__init__(api, coordinator, description)


class AmberOSUtilSensor(AmberOSSensor):
    """Representation a AmberOS Utilisation sensor."""

    @property
    def native_value(self) -> Any | None:
        """Return the state."""
        attr = getattr(self._api.utilisation, self.entity_description.key)
        if callable(attr):
            attr = attr()
        if attr is None:
            return None

        # Data (RAM)
        if self.native_unit_of_measurement == DATA_MEGABYTES:
            return round(attr / 1024.0 ** 2, 1)

        # Network
        if self.native_unit_of_measurement == DATA_RATE_KILOBYTES_PER_SECOND:
            return round(attr / 1024.0, 1)

        # CPU load average
        if self.native_unit_of_measurement == ENTITY_UNIT_LOAD:
            return round(attr / 100, 2)

        return attr

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return bool(self._api.utilisation)

class AmberOSStorageSensor(LwAmberOSDeviceEntity, AmberOSSensor):
    """Representation a AmberOS Storage sensor."""

    entity_description: AmberOSSensorEntityDescription

    def __init__(
        self,
        api: AmberOSApi,
        coordinator: DataUpdateCoordinator[dict[str, dict[str, Any]]],
        description: AmberOSSensorEntityDescription,
        device_id: str | None = None,
    ) -> None:
        """Initialize the AmerOS storage sensor entity."""
        super().__init__(api, coordinator, description, device_id)

    @property
    def native_value(self) -> Any | None:
        """Return the state."""
        attr = getattr(self._api.storage, self.entity_description.key)(self._device_id)
        if attr is None:
            return None

        # Data (disk space)
        if self.native_unit_of_measurement == DATA_TERABYTES:
            return round(attr / 1024.0 ** 4, 2)

        if self.native_unit_of_measurement == DATA_GIGABYTES:
            return round(attr / 1024.0 ** 3, 2)

        return attr

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return storage details."""
        attr = self._attr_extra_state_attributes
        if self.entity_description.key == "disk_status":
            attr.update(getattr(self._api.storage, "get_disk")(self._device_id))
        if self.entity_description.key == "volume_status":
            attr.update(getattr(self._api.storage, "get_volume")(self._device_id))
        return attr


class AmberOSInfoSensor(AmberOSSensor):
    """Representation a AmberOS information sensor."""

    def __init__(
        self,
        api: AmberOSApi,
        coordinator: DataUpdateCoordinator[dict[str, dict[str, Any]]],
        description: AmberOSSensorEntityDescription,
    ) -> None:
        """Initialize the AmberOS Info entity."""
        super().__init__(api, coordinator, description)
        self._previous_uptime: str | None = None
        self._last_boot: datetime | None = None

    @property
    def native_value(self) -> Any | None:
        """Return the state."""
        attr = getattr(self._api.information, self.entity_description.key)
        if attr is None:
            return None

        return attr

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return info details."""
        attr = self._attr_extra_state_attributes
        if "status" in self.entity_description.key:
            attr.update(self._api.backup.status_by_check)
        return attr
