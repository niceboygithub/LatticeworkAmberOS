"""Support for AmberOS cast api."""
from __future__ import annotations

from typing import Final, Any
from collections.abc import Iterable

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
)
from homeassistant.components.media_player.const import (
    SUPPORT_NEXT_TRACK,
    SUPPORT_PAUSE,
    SUPPORT_PLAY,
    SUPPORT_PREVIOUS_TRACK,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_STOP,
    SUPPORT_TURN_OFF,
    SUPPORT_TURN_ON,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
    SUPPORT_PLAY_MEDIA,
    SUPPORT_BROWSE_MEDIA,
    REPEAT_MODE_ALL,
    REPEAT_MODE_OFF,
    REPEAT_MODE_ONE
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_PAUSED, STATE_PLAYING
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import AmberOSApi
from latticework_amberos.api.amberos_cast_api import AmberOSCast
from latticework_amberos.const import (
    AMBEROS_API,
    ATTR_MANUFACTURER,
    COORDINATOR_CAST,
    DOMAIN,
)

SUPPORT_AMBEROS_CAST: Final = (
    SUPPORT_PAUSE
    | SUPPORT_VOLUME_STEP
    | SUPPORT_VOLUME_MUTE
    | SUPPORT_VOLUME_SET
    | SUPPORT_PREVIOUS_TRACK
    | SUPPORT_NEXT_TRACK
    | SUPPORT_TURN_ON
    | SUPPORT_TURN_OFF
    | SUPPORT_SELECT_SOURCE
    | SUPPORT_PLAY
    | SUPPORT_STOP
    | SUPPORT_PLAY_MEDIA
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AmberOS Player from a config_entry."""

    data = hass.data[DOMAIN][entry.unique_id]
    api: AmberOSApi = data[AMBEROS_API]
    coordinator = data[COORDINATOR_CAST]

    unique_id = entry.unique_id
    default_name = f"{api.network.hostname} Cast Player"

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

    async_add_entities(
        [AmberOSCastMediaPlayer(hass, api, coordinator, default_name, unique_id, device_info)]
    )


class AmberOSCastMediaPlayer(CoordinatorEntity, MediaPlayerEntity):
    """Representation of a AmberOS Cast Player."""

    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_supported_features = SUPPORT_AMBEROS_CAST

    def __init__(
        self,
        hass,
        api,
        coordinator,
        name: str,
        unique_id: str,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the entity."""
        self._attr_device_info = device_info
        self._attr_name = name
        self._attr_unique_id = unique_id
        self.hass = hass
        self.api = api
        self.coordinator = coordinator
        self.state_lock = coordinator.state_lock
        self.audio_output: str | None = None
        self._media_list = {}

        super().__init__(coordinator)

    async def async_added_to_hass(self) -> None:
        """Register entity for updates from API."""
        self.async_on_remove(
            self.api.subscribe(AmberOSCast.API_KEY, self._attr_unique_id)
        )
        await super().async_added_to_hass()

    @property
    def state(self) -> str | None:
        """Return the state of the device."""
        if self.api.cast.is_on:
            return STATE_PLAYING if self.api.cast.playing else STATE_PAUSED
        return STATE_OFF

    @property
    def source(self) -> str | None:
        """Return the current input source."""
        return self.api.cast.source

    @property
    def source_list(self) -> list[str]:
        """List of available input sources."""
        return self.api.cast.source_list

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        return self.api.cast.volume_level

    @property
    def is_volume_muted(self) -> bool:
        """Boolean if volume is currently muted."""
        return self.api.cast.muted

    @property
    def media_title(self) -> str | None:
        """Title of current playing media."""
        return self.api.cast.media_title

    @property
    def media_content_id(self) -> str | None:
        """Content ID of current playing media."""
        return self.api.cast.channel_name

    @property
    def media_duration(self) -> int | None:
        """Duration of current playing media in seconds."""
        return self.api.cast.duration

    async def async_request_refresh(self) -> None:
        """ request refresh """
        self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the device on."""
        async with self.state_lock:
            await self.hass.async_add_executor_job(
                self.api.cast.turn_on
            )
            await self.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn the device off."""
        async with self.state_lock:
            await self.hass.async_add_executor_job(
                self.api.cast.turn_off
            )
            await self.async_request_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        async with self.state_lock:
            await self.hass.async_add_executor_job(
                self.api.cast.set_volume_level, volume, self.audio_output
            )
            await self.async_request_refresh()

    async def async_volume_up(self) -> None:
        """Send volume up command."""
        async with self.state_lock:
            await self.hass.async_add_executor_job(
                self.api.cast.volume_up, self.audio_output
            )
            await self.async_request_refresh()

    async def async_volume_down(self) -> None:
        """Send volume down command."""
        async with self.state_lock:
            await self.hass.async_add_executor_job(
                self.api.cast.volume_down, self.audio_output
            )
            await self.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        """Send mute command."""
        async with self.state_lock:
            await self.hass.async_add_executor_job(
                self.api.cast.volume_mute, mute
            )
            await self.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        """Set the input source."""
        async with self.state_lock:
            await self.api.cast.async_select_source(source)
            await self.async_request_refresh()
        self.audio_output = source

    async def async_media_play(self) -> None:
        """Send play command."""
        async with self.state_lock:
            await self.hass.async_add_executor_job(
                self.api.cast.media_play
            )
            await self.async_request_refresh()

    async def async_media_pause(self) -> None:
        """Send pause command."""
        async with self.state_lock:
            await self.hass.async_add_executor_job(
                self.api.cast.media_pause
            )
            await self.async_request_refresh()

    async def async_media_stop(self) -> None:
        """Send media stop command to media player."""
        async with self.state_lock:
            await self.hass.async_add_executor_job(
                self.api.cast.media_stop
            )
            await self.async_request_refresh()

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        async with self.state_lock:
            await self.hass.async_add_executor_job(
                self.api.cast.media_next_track
            )
            await self.async_request_refresh()

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        async with self.state_lock:
            await self.hass.async_add_executor_job(
                self.api.cast.media_previous_track
            )
            await self.async_request_refresh()

    async def async_media_seek(self, position) -> None:
        """Send seek command."""
        async with self.state_lock:
            await self.hass.async_add_executor_job(
                self.api.cast.media_seek, position
            )
            await self.async_request_refresh()

    async def async_play_media(
        self, media_type: str, media_id: str, **kwargs: Any
    ) -> None:
        """Send the play_media command to the media player."""
        async with self.state_lock:
            sid = self.hass.data.get("core.uuid", "0")
            await self.hass.async_add_executor_job(
                self.api.cast.play_media, sid, media_type, media_id, True
            )
            await self.async_request_refresh()

    async def set_repeat(self, repeat: str) -> None:
        """Set repeat mode."""
        if repeat == REPEAT_MODE_ALL:
            play_mode = 2
        elif repeat == REPEAT_MODE_ONE:
            play_mode = 1
        else:
            play_mode = 0
        async with self.state_lock:
            await self.hass.async_add_executor_job(
                self.api.cast.set_repeat, play_mode
            )
            await self.async_request_refresh()

