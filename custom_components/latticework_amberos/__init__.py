"""The Latticework AmberOS component."""
from __future__ import annotations
import asyncio

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.debounce import Debouncer
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_HOST,
    CONF_ENTITY_ID,
    CONF_FILENAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SSL,
    CONF_TIMEOUT,
    CONF_USERNAME
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from latticework_amberos.latticework_amberos import LatticeworkAmberOS
from latticework_amberos.exceptions import (
    AmberOSLoginInvalidException,
    AmberOSFileIndexNotEnable,
    AmberOSFileIndexNotFound
)
from latticework_amberos.api.amberos_information_api import AmberOSInformation
from latticework_amberos.api.amberos_network_api import AmberOSNetwork
from latticework_amberos.api.amberos_system_api import AmberOSSystem
from latticework_amberos.api.amberos_security_api import AmberOSSecurity
from latticework_amberos.api.amberos_storage_api import AmberOSStorage
from latticework_amberos.api.amberos_update_api import AmberOSUpdate
from latticework_amberos.api.amberos_utilization_api import AmberOSUtilization
from latticework_amberos.api.amberos_backup_api import AmberOSBackup
from latticework_amberos.api.amberos_cast_api import AmberOSCast
from latticework_amberos.const import (
    ATTRIBUTION,
    AMBEROS_API,
    CONF_DEVICE_TOKEN,
    CONF_REASON,
    CONF_SERIAL,
    COORDINATOR_CAST,
    COORDINATOR_CENTRAL,
    DEFAULT_CAST_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    SERVICE_CAST_PLAY,
    SERVICE_REBOOT,
    SERVICE_SHUTDOWN,
    SERVICES,
    SYSTEM_LOADED,
    UNDO_UPDATE_LISTENER,
    AmberOSSensorEntityDescription,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Latticework AmberOS sensors."""

    api = AmberOSApi(hass, entry)
    try:
        await api.async_setup()
    except (
        AmberOSLoginInvalidException
    ):
        _LOGGER.error("AmberOSLoginInvalidException")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.unique_id] = {
        UNDO_UPDATE_LISTENER: entry.add_update_listener(_async_update_listener),
        AMBEROS_API: api,
        SYSTEM_LOADED: True,
    }

    # Services
    await _async_setup_services(hass)

    async def async_coordinator_update_data_cast() -> None:
        """Fetch all device and sensor data from api."""
        try:
            await api.async_cast_update()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        return None

    hass.data[DOMAIN][entry.unique_id][COORDINATOR_CAST] = AmberOSCastCoordinator(
        hass,
        _LOGGER,
        name=f"{entry.unique_id}_cast",
        update_method=async_coordinator_update_data_cast,
        update_interval=timedelta(seconds=DEFAULT_CAST_SCAN_INTERVAL),
    )

    async def async_coordinator_update_data_central() -> None:
        """Fetch all device and sensor data from api."""
        try:
            await api.async_update()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        return None

    hass.data[DOMAIN][entry.unique_id][COORDINATOR_CENTRAL] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{entry.unique_id}_central",
        update_method=async_coordinator_update_data_central,
        update_interval=timedelta(
            minutes=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        ),
    )

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Latticewokr AmberOS sensors."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN][entry.unique_id]
        entry_data[UNDO_UPDATE_LISTENER]()
        await entry_data[AMBEROS_API].async_unload()
        hass.data[DOMAIN].pop(entry.unique_id)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

async def _async_setup_services(hass: HomeAssistant) -> None:
    """Service handler setup."""

    async def service_handler(call: ServiceCall) -> None:
        """Handle service call."""
        serial = call.data.get(CONF_SERIAL)
        reason = call.data.get(CONF_REASON)
        amberos_devices = hass.data[DOMAIN]
        filepath = call.data.get(CONF_FILENAME)
        entity_id = call.data.get(CONF_ENTITY_ID)

        amberos_device = None
        if serial:
            amberos_device = amberos_devices.get(serial)
        elif len(amberos_devices) == 1:
            amberos_device = next(iter(amberos_devices.values()))
            serial = next(iter(amberos_devices))
        else:
            if call.service == SERVICE_CAST_PLAY:
                for _, device in amberos_devices.items():
                    amberos_api = device[AMBEROS_API]
                    if amberos_api.network.hostname.replace("-", "_") in entity_id[0]:
                        await amberos_api.async_cast_play(f"/share/{filepath}")
                        return
            else:
                _LOGGER.error(
                    "More than one AmberOS configured, must specify one of serials %s",
                    sorted(amberos_devices),
                )
                return

        if not amberos_device:
            _LOGGER.error("AmberOS with specified serial %s not found", serial)
            return

        if call.service == SERVICE_CAST_PLAY:
            if  not filepath:
                _LOGGER.error("AmberOS with specified filename %s not found", serial)
                return
        _LOGGER.debug("%s AmberOS with serial %s", call.service, serial)
        amberos_api = amberos_device[AMBEROS_API]
        amberos_device[SYSTEM_LOADED] = False
        if call.service == SERVICE_REBOOT:
            await amberos_api.async_reboot()
        elif call.service == SERVICE_SHUTDOWN:
            await amberos_api.async_shutdown(reason)
        elif call.service == SERVICE_CAST_PLAY:
            await amberos_api.async_cast_play(filepath)

    for service in SERVICES:
        hass.services.async_register(DOMAIN, service, service_handler)

class AmberOSApi:
    """Class to interface with Latticework AmberOS API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the API wrapper class."""
        self._hass = hass
        self._entry = entry
        if entry.data.get(CONF_SSL):
            self.config_url = f"https://{entry.data[CONF_HOST]}"
        else:
            self.config_url = f"http://{entry.data[CONF_HOST]}"

        self.initialized = False
        # AmberOS APIs
        self.amberos: LatticeworkAmberOS = None
        self.information: AmberOSInformation = None
        self.network: AmberOSNetwork = None
        self.security: AmberOSSecurity = None
        self.storage: AmberOSStorage = None
        self.backup: AmberOSBackup = None
        self.system: AmberOSSystem = None
        self.upgrade: AmberOSUpdate = None
        self.utilisation: AmberOSUtilization = None
        self.cast: AmberOSCast = None

        # Should we fetch them
        self._fetching_entities: dict[str, set[str]] = {}
        self._with_information = True
        self._with_security = True
        self._with_storage = True
        self._with_backup = True
        self._with_system = True
        self._with_upgrade = True
        self._with_utilisation = True
        self._with_cast = True

    async def async_setup(self) -> None:
        """Start interacting with the AmberOS."""
        self.amberos = LatticeworkAmberOS(
            self._entry.data[CONF_HOST],
            self._entry.data[CONF_PORT],
            self._entry.data[CONF_USERNAME],
            self._entry.data[CONF_PASSWORD],
            self._entry.data[CONF_SSL],
            timeout=self._entry.options.get(CONF_TIMEOUT),
            device_token=self._entry.data.get(CONF_DEVICE_TOKEN),
        )
        await self._hass.async_add_executor_job(self.amberos.login)

        self._async_setup_api_requests()

        await self._hass.async_add_executor_job(self._fetch_device_configuration)
        await self.async_update()
        self.initialized = True

    @callback
    def subscribe(self, api_key: str, unique_id: str) -> Callable[[], None]:
        """Subscribe an entity to API fetches."""
        _LOGGER.debug("Subscribe new entity: %s", unique_id)
        if api_key not in self._fetching_entities:
            self._fetching_entities[api_key] = set()
        self._fetching_entities[api_key].add(unique_id)

        @callback
        def unsubscribe() -> None:
            """Unsubscribe an entity from API fetches (when disable)."""
            _LOGGER.debug("Unsubscribe entity: %s", unique_id)
            self._fetching_entities[api_key].remove(unique_id)
            if len(self._fetching_entities[api_key]) == 0:
                self._fetching_entities.pop(api_key)

        return unsubscribe

    @callback
    def _async_setup_api_requests(self) -> None:
        """Determine if we should fetch each API, if one entity needs it."""
        # Entities not added yet, fetch all
        if not self._fetching_entities:
            _LOGGER.debug(
                "Entities not added yet, fetch all for '%s'", self._entry.unique_id
            )
            return

        # Determine if we should fetch an API
        self._with_system = bool(self.amberos.apis.get(AmberOSSystem.API_KEY))
        self._with_security = bool(
            self._fetching_entities.get(AmberOSSecurity.API_KEY)
        )
        self._with_storage = bool(self._fetching_entities.get(AmberOSStorage.API_KEY))
        self._with_upgrade = bool(self._fetching_entities.get(AmberOSUpdate.API_KEY))
        self._with_utilisation = bool(
            self._fetching_entities.get(AmberOSUtilization.API_KEY)
        )
        self._with_information = bool(
            self._fetching_entities.get(AmberOSInformation.API_KEY)
        )
        self._with_backup = bool(
            self._fetching_entities.get(AmberOSBackup.API_KEY)
        )
        self._with_cast = bool(
            self._fetching_entities.get(AmberOSCast.API_KEY)
        )

        # Reset not used API, information is not reset since it's used in device_info
        if not self._with_security:
            _LOGGER.debug(
                "Disable security api from being updated for '%s'",
                self._entry.unique_id,
            )
            self.amberos.reset(self.security)
            self.security = None

        if not self._with_storage:
            _LOGGER.debug(
                "Disable storage api from being updatedf or '%s'", self._entry.unique_id
            )
            self.amberos.reset(self.storage)
            self.storage = None

        if not self._with_system:
            _LOGGER.debug(
                "Disable system api from being updated for '%s'", self._entry.unique_id
            )
            self.amberos.reset(self.system)
            self.system = None

        if not self._with_upgrade:
            _LOGGER.debug(
                "Disable upgrade api from being updated for '%s'", self._entry.unique_id
            )
            self.amberos.reset(self.upgrade)
            self.upgrade = None

        if not self._with_utilisation:
            _LOGGER.debug(
                "Disable utilisation api from being updated for '%s'",
                self._entry.unique_id,
            )
            self.amberos.reset(self.utilisation)
            self.utilisation = None

        if not self._with_backup:
            _LOGGER.debug(
                "Disable backup api from being updated for '%s'",
                self._entry.unique_id,
            )
            self.amberos.reset(self.backup)
            self.backup = None

        if not self._with_cast:
            _LOGGER.debug(
                "Disable cast api from being updated for '%s'",
                self._entry.unique_id,
            )
            self.amberos.reset(self.cast)
            self.cast = None

    def _fetch_device_configuration(self) -> None:
        """Fetch initial device config."""
        self.information = self.amberos.information
        self.information.update()
        self.network = self.amberos.network
        self.network.update()

        if self._with_security:
            _LOGGER.debug("Enable security api updates for '%s'", self._entry.unique_id)
            self.security = self.amberos.security

        if self._with_storage:
            _LOGGER.debug("Enable storage api updates for '%s'", self._entry.unique_id)
            self.storage = self.amberos.storage

        if self._with_upgrade:
            _LOGGER.debug("Enable upgrade api updates for '%s'", self._entry.unique_id)
            self.upgrade = self.amberos.upgrade

        if self._with_system:
            _LOGGER.debug("Enable system api updates for '%s'", self._entry.unique_id)
            self.system = self.amberos.system

        if self._with_utilisation:
            _LOGGER.debug(
                "Enable utilisation api updates for '%s'", self._entry.unique_id
            )
            self.utilisation = self.amberos.utilisation

        if self._with_backup:
            _LOGGER.debug("Enable backup api updates for '%s'", self._entry.unique_id)
            self.backup = self.amberos.backup

        if self._with_cast:
            _LOGGER.debug("Enable cast api updates for '%s'", self._entry.unique_id)
            self.cast = self.amberos.cast

    async def async_reboot(self) -> None:
        """Reboot AmberOS."""
        try:
            await self._hass.async_add_executor_job(self.system.reboot)
        except (AmberOSLoginInvalidException) as err:
            _LOGGER.error(
                "Reboot of '%s' not possible, please try again later",
                self._entry.unique_id,
            )
            _LOGGER.debug("Exception:%s", err)

    async def async_shutdown(self, reason=None) -> None:
        """Shutdown AmberOS."""
        try:
            await self._hass.async_add_executor_job(self.system.shutdown, reason)
        except (AmberOSLoginInvalidException) as err:
            _LOGGER.error(
                "Shutdown of '%s' not possible, please try again later",
                self._entry.unique_id,
            )
            _LOGGER.debug("Exception:%s", err)

    async def async_cast_play(self, filename) -> None:
        """AmberOS Cast Play."""
        try:
            sid = self._hass.data.get("core.uuid", "0")
            await self._hass.async_add_executor_job(
                self.cast.play_media, sid, "", filename, False)
        except (AmberOSLoginInvalidException) as err:
            _LOGGER.error(
                "Cast play of '%s' not possible, please try again later",
                self._entry.unique_id,
            )
            _LOGGER.debug("Exception:%s", err)
        except AmberOSFileIndexNotEnable as err:
            _LOGGER.error(
                "File Index is not enabled, please enable it"
            )
            _LOGGER.debug("Exception:%s", err)
        except AmberOSFileIndexNotFound as err:
            _LOGGER.error(
                "Cast play on which '%s' is not found, please try again later",
                filename,
            )
            _LOGGER.debug("Exception:%s", err)

    async def async_unload(self) -> None:
        """Stop interacting with the AmberOS and prepare for removal from hass."""
        try:
            await self._hass.async_add_executor_job(self.amberos.logout)
        except (AmberOSLoginInvalidException) as err:
            _LOGGER.debug(
                "Logout from '%s' not possible:%s", self._entry.unique_id, err
            )

    async def async_update(self, now: timedelta | None = None) -> None:
        """Update function for updating API information."""
        _LOGGER.debug("Start data update for '%s'", self._entry.unique_id)
        self._async_setup_api_requests()
        try:
            await self._hass.async_add_executor_job(
                self.amberos.update, self._with_information
            )
        except (AmberOSLoginInvalidException) as err:
            if not self.initialized:
                raise err

            _LOGGER.warning(
                "Connection error during update, fallback by reloading the entry"
            )
            _LOGGER.debug(
                "Connection error during update of '%s' with exception: %s",
                self._entry.unique_id,
                err,
            )
            await self._hass.config_entries.async_reload(self._entry.entry_id)
            return

    async def async_cast_update(self, now: timedelta | None = None) -> None:
        """Update function for updating API cast information."""
        _LOGGER.debug("Start data update for '%s'", self._entry.unique_id)
        try:
            await self._hass.async_add_executor_job(
                self.amberos.cast_update, self._with_cast
            )
        except (AmberOSLoginInvalidException) as err:
            if not self.initialized:
                raise err

            _LOGGER.warning(
                "Connection error during update, fallback by reloading the entry"
            )
            _LOGGER.debug(
                "Connection error during update of '%s' with exception: %s",
                self._entry.unique_id,
                err,
            )
            await self._hass.config_entries.async_reload(self._entry.entry_id)
            return

class LwAmberOSBaseEntity(CoordinatorEntity):
    """Representation of a Latticewokr AmberOS base entry."""

    entity_description: AmberOSSensorEntityDescription
    unique_id: str

    def __init__(
        self,
        api: AmberOSApi,
        coordinator: DataUpdateCoordinator[dict[str, dict[str, Any]]],
        description: AmberOSSensorEntityDescription,
    ) -> None:
        """Initialize the Latticework AmberOS entity."""
        super().__init__(coordinator)
        self.entity_description = description

        self._api = api
        self._attr_name = f"{api.network.hostname} {description.name}"
        self._attr_unique_id: str = (
            f"{api.information.serial}_{description.api_key}:{description.key}"
        )
        self._attr_extra_state_attributes = {ATTR_ATTRIBUTION: ATTRIBUTION}

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._api.information.serial)},
            name="Latticework AmberOS",
            manufacturer="Latticework Inc.",
            model=self._api.information.model,
            sw_version=self._api.information.version_string,
            configuration_url=self._api.config_url,
        )

    async def async_added_to_hass(self) -> None:
        """Register entity for updates from API."""
        self.async_on_remove(
            self._api.subscribe(self.entity_description.api_key, self.unique_id)
        )
        await super().async_added_to_hass()


class LwAmberOSDeviceEntity(LwAmberOSBaseEntity):
    """Representation of a Latticework AmberOS disk or volume entry."""

    def __init__(
        self,
        api: AmberOSApi,
        coordinator: DataUpdateCoordinator[dict[str, dict[str, Any]]],
        description: AmberOSSensorEntityDescription,
        device_id: str | None = None,
    ) -> None:
        """Initialize the Latticework AmberOS disk or volume entity."""
        super().__init__(api, coordinator, description)
        self._device_id = device_id
        self._device_name: str | None = None
        self._device_manufacturer: str | None = None
        self._device_model: str | None = None
        self._device_firmware: str | None = None
        self._device_type = None

        if "volume" in description.key:
            volume = self._api.storage.get_volume(self._device_id)
            # Volume does not have a name
            self._device_name = volume["uuid"].replace("_", " ").capitalize()
            self._device_manufacturer = "Latticework Inc."
            self._device_model = self._api.information.model
            self._device_firmware = self._api.information.version_string
            self._device_type = (
                volume["raidtype"]
                .replace("_", " ")
                .replace("raid", "RAID")
            )
        elif "disk" in description.key:
            disk = self._api.storage.get_disk(self._device_id)
            self._device_name = disk["name"]
            if len(disk["vendor"]) >= 1:
                self._device_manufacturer = disk["vendor"]
            else:
                self._device_manufacturer = disk["model"].split(" ")[0]
            self._device_model = disk["model"]
            self._device_firmware = disk["fw"]
            self._device_type = disk["type"]
        self._name = (
            f"{self._api.network.hostname} {self._device_name} {description.name}"
        )
        self._attr_unique_id += f"_{self._device_id}"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._api.storage  # type: ignore [no-any-return]

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._api.information.serial}_{self._device_id}")},
            name=f"Latticework AmberOS ({self._device_name} - {self._device_type})",
            manufacturer=self._device_manufacturer,
            model=self._device_model,
            sw_version=self._device_firmware,
            via_device=(DOMAIN, self._api.information.serial),
            configuration_url=self._api.config_url,
        )

class AmberOSCastCoordinator(DataUpdateCoordinator[None]):
    """Representation of a AmberOS Cast Coordinator.
    An instance is used per device to share the same power state between
    several platforms.
    """

    def __init__(
        self, hass, logger, name, update_method, update_interval
        ):
        self.state_lock = asyncio.Lock()

        super().__init__(
            hass,
            logger,
            name=name,
            update_method=update_method,
            update_interval=update_interval,
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=1.0, immediate=False
            )
        )
