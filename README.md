[![version](https://img.shields.io/github/manifest-json/v/niceboygithub/latticeworkamberos?filename=custom_components%2Flatticeworkamberos%2Fmanifest.json)](https://github.com/niceboygithub/latticeworkamberos/releases/latest)
[![releases](https://img.shields.io/github/downloadsniceboygithub/latticeworkamberos/total)](https://github.com/niceboygithub/latticeworkamberos/releases)
[![stars](https://img.shields.io/github/stars/niceboygithub/latticeworkamberos)](https://github.com/niceboygithub/latticeworkamberos/stargazers)
[![issues](https://img.shields.io/github/issues/niceboygithub/latticeworkamberos)](https://github.com/niceboygithub/latticeworkamberos/issues)
[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg)](https://hacs.xyz)

# Latticework AmberOS

The Latticwork AmberOS integration provides access to various statistics from your Latticework AmberOS.


This integration was based on the Synology DSM integration of Home Assistant to developing.

## Supported devices
| Name                        |    Model        |   Version     |
|  -------------------------  | --------------- | ------------- |
| Latticework Amber           |    AM12111      |    > 1.20     |
| Latticework Amber X         |    AL1111Y      |    > 1.10     |


* Sensors
  - amberos status
  - memory utilisation
  - network status
  - disk status
  - volume status
* Binary Sensors
  - amberos update status
  - disk status
* Media Player
  - cast


## Installation

You can install component with [HACS](https://hacs.xyz/) custom repo: HACS > Integrations > 3 dots (upper top corner) > Custom repositories > URL: `niceboygithub/LatticeworkAmberOS` > Category: Integration

Or download and manually copy `latticework_amberos` folder to `custom_components` folder in your Home Assistant config folder.

Then restart your Homee Assistant.

## Configuration

Latticework Amber/AmberX can be auto-discovered by Home Assistant. If an instance was found, it will be shown as “Discovered”, which you can select to set it up right away.

You can also use manually configure.

> [⚙️ Configuration](https://my.home-assistant.io/redirect/config) > [🧩 Integrations](https://my.home-assistant.io/redirect/integrations) > [➕ Add Integration](https://my.home-assistant.io/redirect/config_flow_start?domain=latticework_amberor) > 🔍 Search `Latticework AmberOS`

Or click: [![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=latticework_amberos)

### Add deivce via account/password

Enter the account (default: admin) and the password

## Platform services

### Service `Latticework_AmberOS.reboot`

Reboot the specified AmberOS by `serial`.


| Service data attribute    | Optional | Description                                                          |
|---------------------------|----------|----------------------------------------------------------------------|
| `serial`                  |       no | The serial of AmberOS                 |


### Service `Latticework_AmberOS.shutdown`

Shutdown the specified AmberOS by `serial`.


| Service data attribute    | Optional | Description                                                          |
|---------------------------|----------|----------------------------------------------------------------------|
| `serial`                  |       no | The serial of AmberOS                 |


### Service `Latticework_AmberOS.play_media`

Cast Mediay in Amber/AmberX by `filename`.


| Service data attribute    | Optional | Description                                                          |
|---------------------------|----------|----------------------------------------------------------------------|
| `filename`                |       yes | The filename with path for playing, it will automatic search the first match in your Amber/AmberX. The path likes (/Music, /Photos, /Videos, /VPHome/admin/MyDocuments)                |

