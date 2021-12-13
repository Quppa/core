"""Platform for sensor integration."""

import binascii
import time
import datetime

from bluepy import btle
import logging

from .const import DOMAIN

from homeassistant.helpers.entity import Entity

from homeassistant.components.sensor import (
    DEVICE_CLASS_ENERGY,
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
    SensorEntityDescription,
    StateType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DEVICE_CLASS_POWER,
    ENERGY_KILO_WATT_HOUR,
    POWER_KILO_WATT,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    POWERPAL_SERVICE,
    BATTERY_SERVICE,
    PowerpalCharacteristics,
)

_LOGGER = logging.getLogger(__name__)

TIMEOUT: int = 60

measurement_handle = None
pulse_handle = None


class MyDelegate(btle.DefaultDelegate):
    def __init__(self):
        _LOGGER.info("init")
        btle.DefaultDelegate.__init__(self)
        # ... initialise here

    def handleNotification(self, cHandle, data):
        if cHandle == measurement_handle:
            timestamp = int.from_bytes(data[0:4], byteorder="little", signed=False)
            reading = int.from_bytes(data[4:6], byteorder="little", signed=False)
            date = datetime.datetime.fromtimestamp(timestamp).isoformat()
            _LOGGER.info(
                f"Measurement data: {binascii.hexlify(data)}, {timestamp}, {date}, {reading}"
            )
        elif cHandle == pulse_handle:
            _LOGGER.info(f"Measurement data: {binascii.hexlify(data)}")
        else:
            _LOGGER.info(f"{cHandle}: {binascii.hexlify(data)}")
        # ... perhaps check cHandle
        # ... process 'data'


class PowerpalDataCoordinator(DataUpdateCoordinator):

    should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the data object."""
        self.entry = entry
        if self.type == TYPE_EAGLE_100:
            self.model = "EAGLE-100"
            update_method = self._async_update_data_100
        else:
            self.model = "EAGLE-200"
            update_method = self._async_update_data_200

        super().__init__(
            hass,
            _LOGGER,
            name=entry.data[CONF_CLOUD_ID],
            update_interval=timedelta(seconds=30),
            update_method=update_method,
        )

    @property
    def cloud_id(self):
        """Return the cloud ID."""
        return self.entry.data[CONF_CLOUD_ID]

    @property
    def type(self):
        """Return entry type."""
        return self.entry.data[CONF_TYPE]

    @property
    def hardware_address(self):
        """Return hardware address of meter."""
        return self.entry.data[CONF_HARDWARE_ADDRESS]

    @property
    def is_connected(self):
        """Return if the hub is connected to the electric meter."""
        if self.eagle200_meter:
            return self.eagle200_meter.is_connected

        return True

    async def _async_update_data_200(self):
        """Get the latest data from the Eagle-200 device."""
        if (eagle200_meter := self.eagle200_meter) is None:
            hub = aioeagle.EagleHub(
                aiohttp_client.async_get_clientsession(self.hass),
                self.cloud_id,
                self.entry.data[CONF_INSTALL_CODE],
                host=self.entry.data[CONF_HOST],
            )
            eagle200_meter = aioeagle.ElectricMeter.create_instance(
                hub, self.hardware_address
            )
            is_connected = True
        else:
            is_connected = eagle200_meter.is_connected

        async with async_timeout.timeout(30):
            data = await eagle200_meter.get_device_query()

        if self.eagle200_meter is None:
            self.eagle200_meter = eagle200_meter
        elif is_connected and not eagle200_meter.is_connected:
            _LOGGER.warning("Lost connection with electricity meter")

        _LOGGER.debug("API data: %s", data)
        return {var["Name"]: var["Value"] for var in data.values()}

    async def _async_update_data_100(self):
        """Get the latest data from the Eagle-100 device."""
        try:
            data = await self.hass.async_add_executor_job(self._fetch_data_100)
        except UPDATE_100_ERRORS as error:
            raise UpdateFailed from error

        _LOGGER.debug("API data: %s", data)
        return data


class PowerpalSensor(CoordinatorEntity, SensorEntity):
    """Implementation of the Powerpal sensor."""

    coordinator: PowerpalDataCoordinator

    def __init__(self, entity_description):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = entity_description

    @property
    def unique_id(self) -> str | None:
        """Return unique ID of entity."""
        return f"{self.coordinator.cloud_id}-${self.coordinator.hardware_address}-{self.entity_description.key}"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.is_connected

    @property
    def native_value(self) -> StateType:
        """Return native value of the sensor."""
        return self.coordinator.data.get(self.entity_description.key)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.cloud_id)},
            manufacturer="Powerpal",
            model=self.coordinator.model,
            name=self.coordinator.model,
        )

    @property
    def should_poll(self):
        """No polling needed."""
        return False


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        PowerpalSensor(
            coordinator,
            SensorEntityDescription(
                key="powerpal:Pulse",
                name="Pulses",
                native_unit_of_measurement=f"{ENERGY_KILO_WATT_HOUR}",
                state_class=STATE_CLASS_TOTAL_INCREASING,
            ),
        )
    ]

    async_add_entities(entities)


class PowerpalHelper:
    """TODO"""

    def __init__(self, mac, pairing_code, impulse_rate):
        """Init"""
        self.mac = mac
        self.pairing_code = pairing_code
        self.impulse_rate = impulse_rate

    def scan(self):
        scanner = btle.Scanner()
        devices = scanner.scan(TIMEOUT)
        for device in devices:
            device_name = device.getValueText(9)
            if device_name and device_name.startswith("Powerpal "):
                _LOGGER.info(
                    f"Device: {device.addr}, {device.addrType}, {device.iface}, {device.rssi}, {device.connectable}, {device.updateCount}, {device.getDescription(9)}, {device.getValueText(9)}, {device.getScanData()}"
                )

    async def set_up(self):
        """Connect to and validate device and complete pairing process."""

        global measurement_handle

        _LOGGER.info(f"mac: {self.mac}")

        # scanner = btle.Scanner()
        # devices = scanner.scan(TIMEOUT)
        # for device in devices:
        # _LOGGER.info(
        #    #
        #    f"Device: {device.addr}, {device.addrType}, {device.iface}, {device.rssi}, {device.connectable}, {device.updateCount}"
        # )
        # device_name = device.getValueText(9)
        # if device_name and device_name.startswith("Powerpal "):
        # _LOGGER.info(
        #    f"Device: {device.addr}, {device.addrType}, {device.iface}, {device.rssi}, {device.connectable}, {device.updateCount}, {device.getDescription(9)}, #{device.getValueText(9)}, {device.getScanData()}"
        # )

        delegate = MyDelegate()

        try:
            peripheral = btle.Peripheral(
                self.mac, addrType=btle.ADDR_TYPE_RANDOM
            ).withDelegate(delegate)

            _LOGGER.info(peripheral)

            # peripheral.setSecurityLevel("medium")
            # try:
            #    peripheral.pair()
            # except Exception as ex:
            #    _LOGGER.info(ex)

            #
            battery_service = peripheral.getServiceByUUID(BATTERY_SERVICE)

            _LOGGER.info(battery_service)

            battery_characteristics = battery_service.getCharacteristics()

            battery_characteristics_lookup = {
                str(c.uuid).upper(): c for c in battery_characteristics
            }

            print(battery_characteristics_lookup)

            for uuid, characteristic in battery_characteristics_lookup.items():
                print(
                    f"{uuid} ({characteristic.getHandle()}): {characteristic.propertiesToString()}"
                )

            result = battery_characteristics_lookup[
                PowerpalCharacteristics.BATTERY
            ].read()
            _LOGGER.info(result)

            service = peripheral.getServiceByUUID(POWERPAL_SERVICE)

            _LOGGER.info(service)

            characteristics = service.getCharacteristics()

            characteristics_lookup = {str(c.uuid).upper(): c for c in characteristics}

            print(characteristics_lookup)

            for uuid, characteristic in characteristics_lookup.items():
                print(
                    f"{uuid} ({characteristic.getHandle()}): {characteristic.propertiesToString()}"
                )

            # Authenticate with the pairing code (so named by Powerpal)
            pairing_code_bytes = self.pairing_code.to_bytes(4, byteorder="little")

            _LOGGER.info(
                f"pairing_code: {self.pairing_code} ({binascii.hexlify(pairing_code_bytes)})"
            )

            # result = characteristics_lookup[PowerpalCharacteristics.PAIRING_CODE].write(
            #    pairing_code_bytes
            # )

            result = characteristics_lookup[PowerpalCharacteristics.PAIRING_CODE].write(
                pairing_code_bytes, withResponse=True
            )
            _LOGGER.info(result)

            result = characteristics_lookup[PowerpalCharacteristics.TIME].read()
            _LOGGER.info(
                f"time: {binascii.hexlify(result)}, {int.from_bytes(result, byteorder='little')}"
            )
            result = characteristics_lookup[
                PowerpalCharacteristics.LED_SENSITIVITY
            ].read()
            _LOGGER.info(
                f"ledSensitivity: {binascii.hexlify(result)}, {int.from_bytes(result, byteorder='little')}"
            )
            result = characteristics_lookup[PowerpalCharacteristics.UUID].read()
            _LOGGER.info(f"uuid: {binascii.hexlify(result)}")
            result = characteristics_lookup[
                PowerpalCharacteristics.SERIAL_NUMBER
            ].read()
            _LOGGER.info(
                f"serialNumber: {binascii.hexlify(result)}, {int.from_bytes(result, byteorder='little')}"
            )
            result = characteristics_lookup[PowerpalCharacteristics.PAIRING_CODE].read()
            _LOGGER.info(
                f"pairingCode: {binascii.hexlify(result)}, {int.from_bytes(result, byteorder='little')}"
            )
            result = characteristics_lookup[PowerpalCharacteristics.MEASUREMENT].read()
            _LOGGER.info(f"measurement: {binascii.hexlify(result)}")
            result = characteristics_lookup[PowerpalCharacteristics.PULSE].read()
            _LOGGER.info(
                f"pulse: {binascii.hexlify(result)}, {int.from_bytes(result, byteorder='little')}"
            )
            result = characteristics_lookup[
                PowerpalCharacteristics.MILLIS_SINCE_LAST_PULSE
            ].read()
            _LOGGER.info(
                f"millisSinceLastPulse: {binascii.hexlify(result)}, {int.from_bytes(result, byteorder='little')}"
            )
            result = characteristics_lookup[PowerpalCharacteristics.FIRST_REC].read()
            first = result[0:4]
            last = result[4:8]
            _LOGGER.info(
                f"firstRec: {binascii.hexlify(result)}, {int.from_bytes(first, byteorder='little')}, {int.from_bytes(last, byteorder='little')}"
            )
            result = characteristics_lookup[
                PowerpalCharacteristics.MEASUREMENT_ACCESS
            ].read()
            _LOGGER.info(f"measurementAccess: {binascii.hexlify(result)}")
            result = characteristics_lookup[
                PowerpalCharacteristics.READING_BATCH_SIZE
            ].read()
            _LOGGER.info(f"readingBatchSize: {binascii.hexlify(result)}")

            # await client.write_gatt_char(characteristics["measurementAccess"], combined_bytes)
            pulse_handle = characteristics_lookup[
                PowerpalCharacteristics.PULSE
            ].getHandle()

            _LOGGER.info(f"pulse_handle: {pulse_handle}")

            # start notifications for pulse
            pulse_handle_cccd = pulse_handle + 1

            result = peripheral.writeCharacteristic(
                pulse_handle_cccd, bytes([0x01, 0x00]), withResponse=True
            )

            _LOGGER.info(result)

            measurement_handle = characteristics_lookup[
                PowerpalCharacteristics.MEASUREMENT
            ].getHandle()

            _LOGGER.info(f"measurement_handle: {measurement_handle}")

            # start notifications for measurement
            measurement_handle_cccd = measurement_handle + 1

            # result = peripheral.writeCharacteristic(
            #    measurement_handle_cccd, bytes([0x01, 0x00]), withResponse=True
            # )

            # _LOGGER.info(result)

            date_range = first + last

            _LOGGER.info(f"date_range: {binascii.hexlify(date_range)}")

            # from_ms = int(time.time() - 14400).to_bytes(4, byteorder="little")
            # to_ms = int(time.time() - 1440).to_bytes(4, byteorder="little")
            from_ms = int(time.time() - 1440).to_bytes(4, byteorder="little")
            to_ms = int(time.time()).to_bytes(4, byteorder="little")

            date_range = from_ms + to_ms

            _LOGGER.info(f"date_range: {binascii.hexlify(date_range)}")

            # result = characteristics_lookup[
            #    PowerpalCharacteristics.MEASUREMENT_ACCESS
            # ].write(date_range, withResponse=True)

            # _LOGGER.info(result)

            for i in range(100):
                if peripheral.waitForNotifications(1.0):
                    # handleNotification() was called
                    _LOGGER.info(f"handleNotification {i}")

                _LOGGER.info(f"Waiting... {i}")
                # Perhaps do something else here

        finally:
            peripheral.disconnect()

        return True

        # devices = await bleak.BleakScanner.discover(timeout=TIMEOUT)
        # for device in devices:
        #     _LOGGER.info(device)

        # device = await bleak.BleakScanner.find_device_by_address(
        #     self.mac, timeout=TIMEOUT
        # )

        # _LOGGER.info(f"device: {device}")

        # if not device:s
        #     raise bleak.BleakError(
        #         f"A device with address {self.mac} could not be found."
        #     )

        # async with bleak.BleakClient(device, timeout=TIMEOUT) as client:
        #     _LOGGER.info(f"client.is_connected: {client.is_connected}")

        #     # Ensure Powerpal service is present
        #     services = await client.get_services(timeout=TIMEOUT)

        #     _LOGGER.info(f"services: {services}")

        #     if not services.get_service(POWERPAL_SERVICE):
        #         raise bleak.BleakError(f"Missing Powerpal service {POWERPAL_SERVICE}")

        #     # Pair with the device (in the normal Bluetooth sense)
        #     paired = await client.pair(protection_level=2, timeout=TIMEOUT)

        #     _LOGGER.info(f"paired: {paired}")

        #     if not paired:
        #         raise bleak.BleakError(f"Failed to pair")

        #     # Authenticate with the pairing code (so named by Powerpal)
        #     pairing_code_bytes = self.pairing_code.to_bytes(4, byteorder="little")

        #     _LOGGER.info(
        #         f"pairing_code: {self.pairing_code} ({binascii.hexlify(pairing_code_bytes)})"
        #     )

        #     await client.write_gatt_char(
        #         PowerpalCharacteristics.PAIRING_CODE, pairing_code_bytes
        #     )

        #     result = await client.read_gatt_char(PowerpalCharacteristics.TIME)
        #     _LOGGER.info(
        #         f"time: {binascii.hexlify(result)}, {int.from_bytes(result, byteorder='little')}"
        #     )
        #     result = await client.read_gatt_char(
        #         PowerpalCharacteristics.LED_SENSITIVITY
        #     )
        #     _LOGGER.info(
        #         f"ledSensitivity: {binascii.hexlify(result)}, {int.from_bytes(result, byteorder='little')}"
        #     )
        #     result = await client.read_gatt_char(PowerpalCharacteristics.UUID)
        #     _LOGGER.info(f"uuid: {binascii.hexlify(result)}")
        #     result = await client.read_gatt_char(PowerpalCharacteristics.SERIAL_NUMBER)
        #     _LOGGER.info(
        #         f"serialNumber: {binascii.hexlify(result)}, {int.from_bytes(result, byteorder='little')}"
        #     )
        #     result = await client.read_gatt_char(PowerpalCharacteristics.PAIRING_CODE)
        #     _LOGGER.info(
        #         f"pairingCode: {binascii.hexlify(result)}, {int.from_bytes(result, byteorder='little')}"
        #     )
        #     result = await client.read_gatt_char(PowerpalCharacteristics.MEASUREMENT)
        #     _LOGGER.info(f"measurement: {binascii.hexlify(result)}")
        #     result = await client.read_gatt_char(PowerpalCharacteristics.PULSE)
        #     _LOGGER.info(
        #         f"pulse: {binascii.hexlify(result)}, {int.from_bytes(result, byteorder='little')}"
        #     )
        #     result = await client.read_gatt_char(
        #         PowerpalCharacteristics.MILLIS_SINCE_LAST_PULSE
        #     )
        #     _LOGGER.info(
        #         f"millisSinceLastPulse: {binascii.hexlify(result)}, {int.from_bytes(result, byteorder='little')}"
        #     )
        #     result = await client.read_gatt_char(PowerpalCharacteristics.FIRST_REC)
        #     _LOGGER.info(f"firstRec: {binascii.hexlify(result)}")
        #     result = await client.read_gatt_char(
        #         PowerpalCharacteristics.MEASUREMENT_ACCESS
        #     )
        #     _LOGGER.info(f"measurementAccess: {binascii.hexlify(result)}")
        #     result = await client.read_gatt_char(
        #         PowerpalCharacteristics.READING_BATCH_SIZE
        #     )
        #     _LOGGER.info(f"readingBatchSize: {binascii.hexlify(result)}")

        # return True


# async def async_setup_entry(hass, config_entry, async_add_devices):
#     """Add sensors for passed config_entry in HA."""

# class BatterySensor(Entity):
#     """Representation of a Battery sensor."""

#     def __init__(self, hass_data, location_name, sensor_name):
#         """Initialize the sensor."""
#         self.collector = hass_data[COLLECTOR]
#         self.coordinator = hass_data[COORDINATOR]
#         self.location_name = location_name
#         self.sensor_name = sensor_name
#         self.current_state = None

#     async def async_added_to_hass(self) -> None:
#         """Set up a listener and load data."""
#         self.async_on_remove(
#             self.coordinator.async_add_listener(self._update_callback)
#         )
#         self.async_on_remove(
#             self.coordinator.async_add_listener(self._update_callback)
#         )
#         self._update_callback()

#     @callback
#     def _update_callback(self) -> None:
#         self.async_write_ha_state()

#     @property
#     def should_poll(self) -> bool:
#         """Entities do not individually poll."""
#         return False

#     @property
#     def device_class(self):
#         """Return the name of the sensor."""
#         return SENSOR_NAMES[self.sensor_name][1]

#     @property
#     def unit_of_measurement(self):
#         """Return the unit of measurement."""
#         return SENSOR_NAMES[self.sensor_name][0]

#     async def async_update(self):
#         """Refresh the data on the collector object."""
#         await self.collector.async_update()

# class ObservationSensor(SensorBase):
#     """Representation of a BOM Observation Sensor."""

#     def __init__(self, hass_data, location_name, sensor_name):
#         """Initialize the sensor."""
#         super().__init__(hass_data, location_name, sensor_name)

#     @property
#     def unique_id(self):
#         """Return Unique ID string."""
#         return f"{self.location_name}_{self.sensor_name}"

#     @property
#     def extra_state_attributes(self):
#         """Return the state attributes of the sensor."""
#         attr = self.collector.observations_data["metadata"]
#         attr.update(self.collector.observations_data["data"]["station"])
#         attr[ATTR_ATTRIBUTION] = ATTRIBUTION
#         return attr

#     @property
#     def state(self):
#         """Return the state of the sensor."""
#         if self.sensor_name in self.collector.observations_data["data"] and self.collector.observations_data["data"][self.sensor_name] is not None:
#             self.current_state = self.collector.observations_data["data"][self.sensor_name]
#         return self.current_state

#     @property
#     def name(self):
#         """Return the name of the sensor."""
#         return f"{self.location_name} {self.sensor_name.replace('_', ' ').title()}"
