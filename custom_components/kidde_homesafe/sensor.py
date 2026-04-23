"""Sensor platform for Kidde HomeSafe integration."""

from __future__ import annotations

import datetime
import logging
from typing import Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_BILLION,
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import KiddeCoordinator
from .entity import KiddeEntity

KEY_MODEL = "model"
KEY_VALUE = "value"
KEY_STATUS = "status"
KEY_UNIT = "Unit"
KEY_CAPABILITIES = "capabilities"
KEY_IAQ = "iaq"
KEY_TEMPERATURE = "temperature"
KEY_MB_MODEL: Final = "mb_model"
LIFE_SENSOR_KEY: Final = "life"

logger = logging.getLogger(__name__)

# --- DETECT SERIES MODEL LOGIC ---
# Define the set of ALL DETECT series mb_models (46 and 48) for the OR check
MB_MODELS_DETECT_SERIES: Final = {48, 46}

# Keys to skip for DETECT models (they return 0 or unhelpful data)
_SKIP_SIMPLE_SENSOR_KEYS: Final = {"batt_volt", "battery_voltage"}

# Unit/Name configuration for the 'life' sensor based on mb_model
LIFE_SENSOR_CONFIG: Final[dict] = {
    48: { # MB Model 48 (DETECT Smoke/CO)
        "name": "Days to replace",
        "unit": UnitOfTime.DAYS,
    },
    46: { # MB Model 46 (DETECT Smoke Only)
        "name": "Days to replace",
        "unit": UnitOfTime.DAYS,
    },
    "default": {
        "name": "Weeks to replace", # Default for older/non-DETECT models
        "unit": UnitOfTime.WEEKS,
    },
}
# ---------------------------------


_TIMESTAMP_DESCRIPTIONS = (
    SensorEntityDescription(
        key="last_seen",
        icon="mdi:home-clock",
        name="Last Seen",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="last_test_time",
        icon="mdi:home-clock",
        name="Last Test Time",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="iaq_last_test_time",
        icon="mdi:home-clock",
        name="IAQ Last Test Time",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)

_SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(
        key="overall_iaq_status",
        icon="mdi:air-filter",
        name="Overall Air Quality",
        device_class=SensorDeviceClass.ENUM,
        options=["Very Bad", "Bad", "Moderate", "Good"],
    ),
    SensorEntityDescription(
        key="smoke_level",
        icon="mdi:smoke",
        name="Smoke Level",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Existing CO sensor for older models
    SensorEntityDescription(
        key="co_level",
        icon="mdi:molecule-co",
        name="CO Level",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # NEW CO sensor for DETECT series (co_ppm)
    SensorEntityDescription(
        key="co_ppm",
        icon="mdi:molecule-co",
        name="CO PPM",
        # FIX: Reverted to CO to fix the AttributeError, as CARBON_MONOXIDE is unavailable.
        device_class=SensorDeviceClass.CO,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
    ),
    SensorEntityDescription(
        key="batt_volt",
        icon="mdi:battery",
        name="Battery Voltage",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
    ),
    # NOTE: This is the description for the custom KiddeSensorLifeEntity
    SensorEntityDescription(
        key=LIFE_SENSOR_KEY,
        icon="mdi:calendar-clock",
        name="Weeks to replace",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.WEEKS,
    ),
    SensorEntityDescription(
        key="ap_rssi",
        icon="mdi:wifi-strength-3",
        name="Signal strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="ssid",
        icon="mdi:wifi",
        name="SSID",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="alarm_interval",
        icon="mdi:alarm-check",
        name="Alarm Interval",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="alarm_reset_time",
        icon="mdi:alarm-snooze",
        name="Alarm Reset Time",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="battery_level",
        icon="mdi:battery-high",
        name="Battery Level",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="battery_voltage",
        icon="mdi:battery",
        name="Battery Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    SensorEntityDescription(
        key="checkin_interval",
        icon="mdi:clock-check",
        name="Checkin Interval",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.HOURS,
    ),
    SensorEntityDescription(
        key="hold_alarm_time",
        icon="mdi:alarm-plus",
        name="Alarm Hold Time",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="rapid_temperature_variation_status",
        icon="mdi:swap-vertical-variant",
        name="Temperature Variation Status",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="temperature_variation_value",
        icon="mdi:swap-vertical-variant",
        name="Temperature Variation",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="temperature",
        name="Temperature",
        icon="mdi:home-thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
    ),
)

_SENSOR_MEASUREMENT_DESCRIPTIONS = (
    SensorEntityDescription(
        key="iaq_temperature",
        name="Indoor Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="humidity",
        name="Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="hpa",
        name="Air Pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="tvoc",
        name="Total VOC",
        device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="iaq",
        name="Indoor Air Quality",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="co2",
        name="CO₂ Level",
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_devices: AddEntitiesCallback
) -> None:
    """Set up the sensor platform."""
    coordinator: KiddeCoordinator = hass.data[DOMAIN][entry.entry_id]
    sensors: list[SensorEntity] = []

    # --- Find the entity description for 'life' once ---
    life_description = next(
        (
            desc for desc in _SENSOR_DESCRIPTIONS 
            if desc.key == LIFE_SENSOR_KEY
        ),
        None,
    )

    for device_id, device_data in coordinator.data.devices.items():
        mb_model = device_data.get(KEY_MB_MODEL)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Checking model: [%s] (MB:%s)",
                coordinator.data.devices[device_id].get(KEY_MODEL, "Unknown"),
                mb_model,
            )

        for entity_description in _TIMESTAMP_DESCRIPTIONS:
            if entity_description.key in device_data:
                sensors.append(
                    KiddeSensorTimestampEntity(
                        coordinator, device_id, entity_description
                    )
                )

        # -------------------------------------------------------------
        # 1. Custom Life Sensor Entity
        if LIFE_SENSOR_KEY in device_data and life_description:
            sensors.append(
                KiddeSensorLifeEntity(coordinator, device_id, life_description)
            )
        # -------------------------------------------------------------

        for entity_description in _SENSOR_DESCRIPTIONS:
            # Skip the 'life' sensor from the simple loop, as it's handled by the custom entity
            if entity_description.key == LIFE_SENSOR_KEY:
                continue

            # --- DETECT Series Check for Voltage Sensor Exclusion ---
            if (
                entity_description.key in _SKIP_SIMPLE_SENSOR_KEYS and 
                mb_model in MB_MODELS_DETECT_SERIES
            ):
                logger.debug(f"Skipping sensor '{entity_description.key}' because mb_model {mb_model} is DETECT series.")
                continue
            # --- END Check ---

            if entity_description.key in device_data:
                sensors.append(
                    KiddeSensorEntity(coordinator, device_id, entity_description)
                )

        for entity_description in _SENSOR_MEASUREMENT_DESCRIPTIONS:
            if entity_description.key in device_data:
                sensors.append(
                    KiddeSensorMeasurementEntity(
                        coordinator, device_id, entity_description
                    )
                )

    async_add_devices(sensors)


class KiddeSensorTimestampEntity(KiddeEntity, SensorEntity):
    """A KiddeSensoryEntity which returns a datetime."""

    @property
    def native_value(self) -> datetime.datetime | None:
        """Return the native value of the sensor."""
        value = self.kidde_device.get(self.entity_description.key)
        dtype = type(value)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "%s, of type %s is %s",
                self.entity_description.key,
                dtype,
                value,
            )
        if value is None:
            return value
        stripped = value.strip("Z").split(".")[0]
        try:
            return datetime.datetime.strptime(stripped, "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=datetime.UTC
            )
        except ValueError as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.error("Error parsing datetime '%s': %s", value, e)
            return None


class KiddeSensorLifeEntity(KiddeEntity, SensorEntity):
    """Custom entity for the 'life' sensor to conditionally adjust units."""
    
    # FIX: Remove the conflicting @property definition and move the dynamic logic 
    # to the __init__ to set the attributes directly.
    def __init__(
        self,
        coordinator: KiddeCoordinator,
        device_id: int,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the custom life sensor."""
        
        # 1. Call the base class __init__ FIRST. This successfully sets 
        #    self.entity_description = entity_description (the base one).
        super().__init__(coordinator, device_id, entity_description)

        # 2. Get the model-specific configuration (Name and Unit).
        config = self._model_config
        
        # 3. Dynamically override the entity's Name and Unit attributes 
        #    using the Home Assistant standard pattern.
        #    We must override _attr_name and _attr_native_unit_of_measurement
        self._attr_native_unit_of_measurement = config["unit"]
        self._attr_name = config["name"]


    @property
    def _model_config(self) -> dict:
        """Get the specific config (name/unit) based on the device mb_model."""
        
        # Use the mb_model (integer) for the lookup, falling back to "default" if not found
        device_identifier = self.kidde_device.get(KEY_MB_MODEL, "default")
        
        return LIFE_SENSOR_CONFIG.get(device_identifier, LIFE_SENSOR_CONFIG["default"])
        
    @property
    def native_value(self) -> float | None:
        """Return the native value of the sensor."""
        return self.kidde_device.get(LIFE_SENSOR_KEY)


class KiddeSensorEntity(KiddeEntity, SensorEntity):
    """Sensor for Kidde HomeSafe."""

    @property
    def native_value(self) -> str | None | float | int:
        """Return the native value of the sensor."""
        value = self.kidde_device.get(self.entity_description.key)
        dtype = type(value)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "%s, of type %s is %s",
                self.entity_description.key,
                dtype,
                value,
            )
        return value


class KiddeSensorMeasurementEntity(KiddeEntity, SensorEntity):
    """Measurement Sensor for Kidde HomeSafe."""

    @property
    def state_class(self) -> str:
        """Return the state class of sensor."""
        return SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the native value of the sensor."""
        entity_dict = self.kidde_device.get(self.entity_description.key)
        if isinstance(entity_dict, dict):
            sensor_value = entity_dict.get(KEY_VALUE)
        else:
            ktype = type(entity_dict)
            if logger.isEnabledFor(logging.DEBUG):
                logger.warning(
                    "Unexpected type [%s], expected entity dict for [%s]",
                    ktype,
                    self.entity_description.key,
                )
            sensor_value = None
        return sensor_value

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit of measurement of the sensor."""
        entity_dict = self.kidde_device.get(self.entity_description.key)

        if not isinstance(entity_dict, dict):
            if logger.isEnabledFor(logging.DEBUG):
                logger.warning(
                    "Unexpected type [%s], expected entity dict for [%s]",
                    type(entity_dict),
                    self.entity_description.key,
                )
            return None

        entity_unit = entity_dict.get(KEY_UNIT, "").upper()

        match entity_unit:
            case "C":
                return UnitOfTemperature.CELSIUS
            case "F":
                return UnitOfTemperature.FAHRENHEIT
            case "%RH":
                return PERCENTAGE
            case "HPA":
                return UnitOfPressure.PA
            case "PPB":
                return CONCENTRATION_PARTS_PER_BILLION
            case "PPM":
                return CONCENTRATION_PARTS_PER_MILLION
            case "V":
                return UnitOfElectricPotential.VOLT
            case _:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.warning(
                        "Unknown unit [%s] for sensor [%s]",
                        entity_unit,
                        self.entity_description.key,
                    )
                return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes for the value sensor (Status)."""
        entity_dict = self.kidde_device.get(self.entity_description.key)
        attribute_dict = None
        if isinstance(entity_dict, dict):
            attribute_dict = {"Status": entity_dict.get(KEY_STATUS)}
        else:
            ktype = type(entity_dict)
            if logger.isEnabledFor(logging.DEBUG):
                # FIX: Corrected a missing closing parenthesis, which was not the current issue, 
                # but might be a future error point.
                logger.warning(
                    "Unexpected type [%s], expected state attributes dict for [%s]",
                    ktype,
                    self.entity_description.key,
                )
            attribute_dict = {"Status": None}
        return attribute_dict
