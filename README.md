# Thames Water Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

# Home Assistant Integration for Thames Water Consumption Data

This Home Assistant integration retrieves water consumption data from Thames Water using their API. It allows you to monitor your water usage directly from your Home Assistant setup without needing additional devices.

You need a Thames Water Smart Meter. The water consumption data provided by this integration is delayed by approximately three days or more. This delay is a characteristic of the Thames Water data system and cannot be altered in this integration.

With these cookies, it then calls the `getSmartWaterMeterConsumptions` API to retrieve the usage data.

## Installation

### Installation through HACS

1. Install the custom component using the Home Assistant Community Store (HACS) by adding the Custom Repository:
https://github.com/pthimon/HA-Thames-Water
2. In the HACS panel, select Thames Water from the repository list and select the DOWNLOAD button.
3. Restart HA
4. Go to Settings > Devices & Services > Add Integration and select Thames Water.

### Manual installation

Copy the `custom_components/thames_water/` directory and all of its files to your `config/custom_components/` directory.

## Configuration

Once installed, restart Home Assistant:

[![Open your Home Assistant instance and show the system dashboard.](https://my.home-assistant.io/badges/system_dashboard.svg)](https://my.home-assistant.io/redirect/system_dashboard/)

Then, add the integration:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=thames_water)


<details>
  <summary>Manually add the Integration</summary>
  Visit the <i>Integrations</i> section in Home Assistant and click the <i>Add</i> button in the bottom right corner. Search for <code>Thames Water</code> and input your credentials. <b>You may need to clear your browser cache before the integration appears in the list.</b>
</details>

## First Run

After installing and adding the integration with your Thames Water credentials:

1. **Backfill historical data** — Go to Settings > Developer Tools > Actions and call `thames_water.fill_historical_data` with a `start_date` (e.g. `2024-01-01`). This fetches all available historical data and **automatically sets the initial meter reading** from the earliest data point.
2. **Check the initial reading** — The `number.thames_water_initial_meter_reading` entity should now show the meter reading at the start of your data. You can adjust it manually if needed.
3. **(Optional) Set your tariff** — The `number.thames_water_cost_per_cubic_metre` entity defaults to £2.7346/m³ (Thames Water's standard rate). Update it if your tariff differs.
4. **Add to Energy dashboard** — See the Energy Management section below.

The sensor will then update automatically at 00:00 and 12:00 every day. Statistics will not be generated until the initial meter reading has been set.

## Cost Tracking

The integration provides a **Thames Water Cost Per Cubic Metre** number entity (`number.thames_water_cost_per_cubic_metre`) that lets you configure the price you pay per cubic metre of water. This defaults to £2.7346/m³ to match Thames Water's published tariff, but can be changed at any time via the UI or an automation.

Cost statistics are available as **thames_water:thameswater_cost** and can be added to the Energy dashboard.

Since the cost entity is a regular Home Assistant entity, you can also update it automatically. For example, you can use the [Scrape](https://www.home-assistant.io/integrations/scrape/) integration to pull the current rate from Thames Water's website and an automation to keep the entity in sync:

Add to `configuration.yaml`:

```yaml
scrape:
  - resource: https://www.thameswater.co.uk/help/account-and-billing/understand-your-bill/metered-customers
    headers:
      User-Agent: "Mozilla/5.0 (X11; Linux x86_64)"
    scan_interval: 86400
    sensor:
      - name: Thames Water Clean Water Rate
        select: "body"
        value_template: >-
          {{ value | regex_findall_index('£([\d.]+) per m3 for clean water') }}
        unit_of_measurement: "£/m³"
        device_class: monetary
```

Then add an automation to update the cost entity when the scraped rate changes. Add the following to `automations.yaml`:

```yaml
- alias: Update Thames Water cost per cubic metre
  trigger:
    - platform: state
      entity_id: sensor.thames_water_clean_water_rate
  action:
    - action: number.set_value
      target:
        entity_id: number.thames_water_cost_per_cubic_metre
      data:
        value: "{{ states('sensor.thames_water_clean_water_rate') }}"
```

## Energy Management

The water statistics can be integrated into HA [Home Energy Management](https://www.home-assistant.io/docs/energy/) using **thames_water:thameswater_consumption** for volume and **thames_water:thameswater_cost** for cost.

It will attempt to fetch the latest data at 00:00 and 12:00 every day.

[![Open your Home Assistant instance and show your Energy configuration panel.](https://my.home-assistant.io/badges/config_energy.svg)](https://my.home-assistant.io/redirect/config_energy/)

![Dashboard](./dashboard.png)

## Credits

This integration is based on the work by [@AyrtonB](https://github.com/AyrtonB):

- [HA-Thames-Water](https://github.com/AyrtonB/HA-Thames-Water) — the original Home Assistant integration
- [Thames-Water](https://github.com/AyrtonB/Thames-Water) — the Thames Water API client library
