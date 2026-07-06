"""Config flow for Matrio Control integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .const import DEFAULT_PORT, DEFAULT_ZONES, DOMAIN, CONF_DEVICE_NAME, CONF_ZONES, CONF_CHILD_ENTITY_MAPPINGS
from .matrio_controller import MatrioController

_LOGGER = logging.getLogger(__name__)

# Placeholder for "None" option in child entity mapping UI
NONE_PLACEHOLDER_VALUE = "_MATRIO_NONE_UNMAPPED_"
NONE_PLACEHOLDER_DISPLAY = "None (Unmapped)"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_DEVICE_NAME, default="Matrio Control"): str,
        vol.Optional(CONF_ZONES, default=DEFAULT_ZONES): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=8)
        ),
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Matrio Control."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return OptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            # Test connection
            controller = MatrioController(
                user_input[CONF_HOST], user_input[CONF_PORT]
            )
            await controller.connect()
            await controller.disconnect()
        except (ConnectionError, TimeoutError) as ex:
            _LOGGER.error("Failed to connect to Matrio device: %s", ex)
            errors["base"] = "cannot_connect"
        except OSError as ex:
            _LOGGER.error("Network or system error connecting to Matrio device: %s", ex)
            errors["base"] = "cannot_connect"

        if not errors:
            return self.async_create_entry(
                title=f"Matrio Control ({user_input[CONF_HOST]})",
                data=user_input
            )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class OptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Matrio Control."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is None:
            # Get all media player entities for selection
            entity_registry = er.async_get(self.hass)
            media_players = []
            
            for entity in entity_registry.entities.values():
                if (entity.domain == "media_player" and 
                    entity.platform != DOMAIN and  # Exclude our own entities
                    not entity.disabled_by):
                    # Get friendly name from current state, fallback to entity registry, then entity_id
                    state = self.hass.states.get(entity.entity_id)
                    if state and state.attributes.get("friendly_name"):
                        name = state.attributes["friendly_name"]
                    elif entity.name:
                        name = entity.name
                    else:
                        name = entity.entity_id
                    
                    media_players.append((entity.entity_id, name))
            
            # Sort by friendly name for better UX
            media_players.sort(key=lambda x: x[1])
            
            # Add "None" option for unmapped zones using explicit placeholder
            media_player_options = [(NONE_PLACEHOLDER_VALUE, NONE_PLACEHOLDER_DISPLAY)] + media_players
            media_player_dict = dict(media_player_options)
            
            # Debug: Log the media player options
            _LOGGER.debug("Media player options: %s", media_player_options[:5])  # First 5 options
            _LOGGER.debug("None placeholder in media_player_dict: %s", NONE_PLACEHOLDER_VALUE in media_player_dict)
            
            # Get current child entity mappings
            current_mappings = self.config_entry.data.get(CONF_CHILD_ENTITY_MAPPINGS, {})
            
            # Get input names from coordinator data
            input_names = {}
            try:
                coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
                if not coordinator:
                    _LOGGER.error("Coordinator not found for config entry %s", self.config_entry.entry_id)
                    return self.async_show_form(
                        step_id="init",
                        errors={"base": "coordinator_unavailable"}
                    )
                    
                if coordinator.data:
                    names_data = coordinator.data.get("inputs", {})
                    if names_data:
                        # Convert from {1: "name1", 2: "name2"} to {"input_1": "name1", "input_2": "name2"}
                        input_names = {f"input_{k}": v for k, v in names_data.items()}
                    _LOGGER.debug("Retrieved input names: %s", input_names)
                else:
                    _LOGGER.warning("Coordinator data not available, using fallback input names")
                    
            except KeyError as e:
                _LOGGER.error("Coordinator not found in hass.data for domain %s, entry %s: %s", 
                            DOMAIN, self.config_entry.entry_id, e)
                return self.async_show_form(
                    step_id="init",
                    errors={"base": "coordinator_unavailable"}
                )
            except (AttributeError, TypeError) as e:
                _LOGGER.error("Invalid coordinator data structure: %s", e)
                return self.async_show_form(
                    step_id="init", 
                    errors={"base": "coordinator_data_error"}
                )
            
            # Create schema with dynamic field names
            num_zones = self.config_entry.data.get(CONF_ZONES, DEFAULT_ZONES)
            schema_dict = {}
            
            try:
                for zone_num in range(1, num_zones + 1):
                    input_key = f"input_{zone_num}"
                    # Use placeholder for unmapped inputs, actual entity for mapped ones
                    current_value = current_mappings.get(input_key, NONE_PLACEHOLDER_VALUE)
                    # Use actual device input name for display
                    input_display_name = input_names.get(input_key, f"Input {zone_num}")
                    
                    # Create a descriptive field name that Home Assistant will use as the label
                    descriptive_key = f"{input_display_name} (Input {zone_num})"
                    # Use vol.In with the media_player_dict which maps values to display names
                    schema_dict[vol.Optional(descriptive_key, default=current_value)] = vol.In(
                        media_player_dict
                    )
                
                data_schema = vol.Schema(schema_dict)
                _LOGGER.debug("Successfully created schema with %d fields", len(schema_dict))
                
            except (KeyError, ValueError, TypeError) as e:
                _LOGGER.error("Error creating options schema: %s", e)
                # Fallback to basic schema
                data_schema = vol.Schema({vol.Optional("error"): str})
                return self.async_show_form(
                    step_id="init",
                    data_schema=data_schema,
                    errors={"base": "schema_error"}
                )
            
            return self.async_show_form(
                step_id="init",
                data_schema=data_schema,
                description_placeholders={"zones": str(num_zones)}
            )
        
        # Process user input - convert descriptive keys back to input_N format
        child_mappings = {}
        
        _LOGGER.debug("Processing options flow user input: %s", user_input)
        _LOGGER.debug("Previous child_mappings: %s", self.config_entry.data.get(CONF_CHILD_ENTITY_MAPPINGS, {}))
        
        # Get all configured zones to ensure we process all inputs, even those set to None
        num_zones = self.config_entry.data.get(CONF_ZONES, DEFAULT_ZONES)
        all_expected_inputs = set()
        
        # Get input names again for processing
        try:
            coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
            if coordinator and coordinator.data:
                names_data = coordinator.data.get("inputs", {})
                if names_data:
                    input_names_for_processing = {f"input_{k}": v for k, v in names_data.items()}
                else:
                    input_names_for_processing = {}
            else:
                input_names_for_processing = {}
        except (KeyError, AttributeError):
            input_names_for_processing = {}
        
        # Build set of all expected input keys based on the form we showed
        for zone_num in range(1, num_zones + 1):
            input_key = f"input_{zone_num}"
            input_display_name = input_names_for_processing.get(input_key, f"Input {zone_num}")
            descriptive_key = f"{input_display_name} (Input {zone_num})"
            all_expected_inputs.add((descriptive_key, input_key))
        
        _LOGGER.debug("Expected inputs: %s", [desc_key for desc_key, _ in all_expected_inputs])
        
        # Process all expected inputs, whether they appear in user_input or not
        for descriptive_key, input_key in all_expected_inputs:
            value = user_input.get(descriptive_key, NONE_PLACEHOLDER_VALUE)  # Default to placeholder if not in user_input
            _LOGGER.debug("Processing key: %s, value: %s", descriptive_key, value)
            
            if value and value != NONE_PLACEHOLDER_VALUE:  # Valid entity mapping
                child_mappings[input_key] = value
                _LOGGER.debug("Mapped %s -> %s: %s", descriptive_key, input_key, value)
            else:  # Placeholder value means explicitly unmapped
                # Explicitly exclude this input from the final mappings
                # (by not adding it to child_mappings, it will be removed)
                _LOGGER.debug("Input %s set to unmapped (will be excluded from config)", input_key)
        
        _LOGGER.debug("New child_mappings (only mapped inputs): %s", child_mappings)
        
        # Update config entry with new child mappings
        # Always replace the entire mapping (this handles both additions and removals)
        new_data = dict(self.config_entry.data)
        if child_mappings:
            new_data[CONF_CHILD_ENTITY_MAPPINGS] = child_mappings
        else:
            # If no mappings, remove the key entirely
            new_data.pop(CONF_CHILD_ENTITY_MAPPINGS, None)
        
        _LOGGER.debug("Updating config entry with data: %s", new_data)
        
        # Update the coordinator directly to avoid full integration reload
        try:
            coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
            coordinator.child_entity_mappings = child_mappings.copy()
            _LOGGER.debug("Updated coordinator child_entity_mappings directly: %s", child_mappings)
            
            # Update the config entry data directly without triggering reload listener
            # We do this by temporarily removing the update listener during the update
            old_listeners = list(self.config_entry.update_listeners)
            self.config_entry.update_listeners.clear()
            
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            
            # Restore the update listeners
            self.config_entry.update_listeners.extend(old_listeners)
            _LOGGER.debug("Config entry updated without triggering reload")
            
            # Manually refresh the coordinator to update entities with new mappings
            await coordinator.async_request_refresh()
            _LOGGER.debug("Coordinator refreshed to apply new child entity mappings")
            
        except (KeyError, AttributeError) as e:
            _LOGGER.warning("Could not update coordinator or config entry: %s", e)
            return self.async_show_form(
                step_id="init",
                errors={"base": "update_failed"}
            )
        
        return self.async_create_entry(title="", data={})
