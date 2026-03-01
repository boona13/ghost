---
name: weather
description: Get current weather and forecasts via wttr.in - no API key needed. Use when the user asks about weather, temperature, forecasts, or conditions for any location.
triggers:
  - weather
  - forecast
  - temperature
  - rain
  - sunny
  - cloudy
  - snow
  - wind
  - humidity
  - "wttr"
tools:
  - shell_exec
priority: 5
---

# Weather Skill

Get current weather conditions and forecasts for any location using wttr.in (free service, no API key required).

## When to Use

**✅ USE this skill when:**
- User asks "What's the weather?" or "What's the weather in [city]?"
- "Will it rain today/tomorrow?"
- "Temperature in [location]"
- "Weather forecast for the week"
- Travel planning weather checks

**❌ DON'T use this skill when:**
- Historical weather data analysis
- Severe weather alerts (use official sources)
- Aviation/marine weather (use specialized services)

## Usage

### Current Weather

```bash
# Simple one-line summary
curl -s "wttr.in/London?format=3"

# Detailed current conditions
curl -s "wttr.in/London?0"

# JSON output for parsing
curl -s "wttr.in/London?format=j1"
```

### Forecasts

```bash
# 3-day forecast (visual)
curl -s "wttr.in/London"

# Week forecast
curl -s "wttr.in/London?format=v2"

# Specific day (0=today, 1=tomorrow, etc.)
curl -s "wttr.in/London?1"
```

### Custom Format

```bash
# Location, condition, temp, feels like, wind, humidity
curl -s "wttr.in/London?format=%l:+%c+%t+(feels+like+%f),+%w+wind,+%h+humidity"

# Just condition and precipitation (for rain check)
curl -s "wttr.in/London?format=%c+%p"
```

### Format Codes

| Code | Meaning |
|------|---------|
| `%c` | Weather condition emoji |
| `%C` | Weather condition text |
| `%t` | Temperature (actual) |
| `%f` | "Feels like" temperature |
| `%w` | Wind |
| `%h` | Humidity |
| `%p` | Precipitation |
| `%l` | Location name |
| `%m` | Moon phase |
| `%P` | Pressure |

### Airport Codes

```bash
# Use 3-letter airport codes
curl -s "wttr.in/JFK?format=3"  # New York JFK
curl -s "wttr.in/LHR?format=3"  # London Heathrow
```

## Examples

**"What's the weather in Tokyo?"**
```bash
curl -s "wttr.in/Tokyo?format=3"
```

**"Will it rain in Seattle tomorrow?"**
```bash
curl -s "wttr.in/Seattle?1" | head -20
```

**"Week forecast for Miami"**
```bash
curl -s "wttr.in/Miami?format=v2"
```

**"Current temp and humidity in my city"** (ask user for city if not provided)
```bash
curl -s "wttr.in/CITY_NAME?format=%l:+%t,+%h+humidity"
```

## Error Handling

When wttr.in fails or returns errors:

```bash
# Check if service is reachable
curl -s --max-time 10 "wttr.in/London?format=3" || echo "Weather service unavailable"

# Handle ambiguous locations (returns list of options)
curl -s "wttr.in/Paris"  # If ambiguous, shows matching locations
# Use specific: "Paris,France" or "Paris,TX" or "Paris,IL"
```

**Common errors:**
- `Unknown location` → Try different spelling or add country/state
- `500` or timeout → Service temporarily down, retry with backoff
- Garbled output → Use `?T` for plain text (no ANSI colors)

## Terminal-Friendly Output

For scripts or terminals without emoji/ANSI support:

```bash
# Plain text, no colors, no emoji
curl -s "wttr.in/London?0&T"

# One-line plain text
curl -s "wttr.in/London?format=3&T"

# JSON (best for parsing programmatically)
curl -s "wttr.in/London?format=j1"
```

## Handling Ambiguous Locations

When a city name matches multiple places:

```bash
# Be specific with country or state
curl -s "wttr.in/Paris,France?format=3"
curl -s "wttr.in/Paris,TX?format=3"
curl -s "wttr.in/Springfield,IL?format=3"

# Use coordinates for precision
curl -s "wttr.in/48.8566,2.3522?format=3"  # Paris, France
```

## Notes

- wttr.in is free and requires no API key
- Supports most global cities and airport codes
- Rate limiting applies (don't make rapid successive calls)
- For ambiguous city names, wttr.in picks the most likely match (often the largest city)
- Unicode/emoji output may vary by terminal
- Add `&T` to any URL for plain text output (no ANSI escape codes)