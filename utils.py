# utils.py
import requests
import re
import json
import streamlit as st
from datetime import datetime, date

def extract_route_request(text):
    """Extract route request details from Ollama response"""
    # Try standard format first
    pattern = r'\[ROUTE_REQUEST\](.*?)\[/ROUTE_REQUEST\]'
    match = re.search(pattern, text, re.DOTALL)
    
    # If no match, try to find unclosed tag
    if not match:
        pattern_unclosed = r'\[ROUTE_REQUEST\](.*?)(?=\n\n|\Z)'
        match = re.search(pattern_unclosed, text, re.DOTALL)
    
    if match:
        content = match.group(1)
        request = {}
        for line in content.split('\n'):
            if ':' in line:
                # Handle "type: walk/run" -> take first option
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                
                # Take first option if multiple given (e.g., "walk/run" -> "walk")
                if '/' in value and key in ['type']:
                    value = value.split('/')[0]
                
                request[key] = value
        return request if request else None
    return None

def get_weather_info(lat, lon):
    """Get current weather information"""
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weathercode,windspeed_10m&temperature_unit=fahrenheit"
        response = requests.get(url, timeout=5)
        data = response.json()
        
        current = data.get('current', {})
        weather_codes = {0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast", 61: "Rain", 71: "Snow"}
        condition = weather_codes.get(current.get('weathercode', 0), "Unknown")
        
        return {
            "temperature": f"{current.get('temperature_2m', 'N/A')}°F",
            "condition": condition,
            "wind_speed": f"{current.get('windspeed_10m', 'N/A')} mph"
        }
    except:
        return {"temperature": "N/A", "condition": "Unable to fetch", "wind_speed": "N/A"}

# --- Geocoding (Nominatim - FREE) ---

def geocode_location(address, city="Athens, Ohio"):
    """Convert address to lat/lon using OpenStreetMap Nominatim (FREE)"""
    try:
        # Add city context for better results
        full_address = f"{address}, {city}" if city.lower() not in address.lower() else address
        
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": full_address,
            "format": "json",
            "limit": 1
        }
        headers = {
            "User-Agent": "TG-Agent-Student-Project/1.0"  # Required by Nominatim
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        if data:
            return {
                "lat": float(data[0]["lat"]),
                "lon": float(data[0]["lon"]),
                "display_name": data[0].get("display_name", address)
            }
        return None
    except Exception as e:
        print(f"Geocoding error for '{address}': {str(e)}")
        return None

def get_walking_route(coordinates, ors_api_key):
    """
    Get real walking route along roads using OpenRouteService (FREE - 2000/day)
    coordinates: list of [lon, lat] pairs (NOTE: ORS uses lon,lat not lat,lon!)
    """
    if not ors_api_key:
        return None
    
    try:
        url = "https://api.openrouteservice.org/v2/directions/foot-walking/geojson"
        headers = {
            "Authorization": ors_api_key,
            "Content-Type": "application/json"
        }
        body = {
            "coordinates": coordinates  # [[lon, lat], [lon, lat], ...]
        }
        
        response = requests.post(url, json=body, headers=headers, timeout=15)
        data = response.json()
        
        if "features" in data and len(data["features"]) > 0:
            geometry = data["features"][0]["geometry"]["coordinates"]
            properties = data["features"][0]["properties"]
            
            # Convert [lon, lat] to [lat, lon] for Folium
            route_coords = [[coord[1], coord[0]] for coord in geometry]
            
            # Extract summary
            summary = properties.get("summary", {})
            distance_km = summary.get("distance", 0) / 1000
            duration_min = summary.get("duration", 0) / 60
            
            return {
                "coordinates": route_coords,
                "distance_miles": round(distance_km * 0.621371, 2),
                "duration_minutes": round(duration_min, 1)
            }
        else:
            print(f"ORS Error: {data}")
            return None
    except Exception as e:
        print(f"Routing error: {str(e)}")
        return None

# --- Gemini Usage Tracking ---

def init_gemini_usage():
    """Initialize Gemini usage tracking in session state"""
    if "gemini_usage" not in st.session_state:
        st.session_state.gemini_usage = {
            "requests_today": 0,
            "tokens_today": 0,
            "last_reset": date.today().isoformat(),
            "last_request_tokens": 0
        }

def reset_daily_usage_if_needed():
    """Reset counters if it's a new day"""
    init_gemini_usage()
    usage = st.session_state.gemini_usage
    
    today = date.today().isoformat()
    if usage["last_reset"] != today:
        usage["requests_today"] = 0
        usage["tokens_today"] = 0
        usage["last_reset"] = today

def track_gemini_usage(response):
    """Track token usage from a Gemini response"""
    reset_daily_usage_if_needed()
    usage = st.session_state.gemini_usage
    
    try:
        metadata = response.usage_metadata
        tokens_used = metadata.total_token_count
        
        usage["requests_today"] += 1
        usage["tokens_today"] += tokens_used
        usage["last_request_tokens"] = tokens_used
    except AttributeError:
        # If usage_metadata not available, just count the request
        usage["requests_today"] += 1
        usage["last_request_tokens"] = 0
    
    return usage

def get_usage_stats():
    """Get current Gemini usage statistics"""
    reset_daily_usage_if_needed()
    usage = st.session_state.gemini_usage
    
    return {
        "requests_today": usage["requests_today"],
        "requests_limit": 1500,
        "tokens_today": usage["tokens_today"],
        "tokens_limit": 1_000_000,
        "last_request_tokens": usage["last_request_tokens"],
        "requests_remaining": 1500 - usage["requests_today"],
        "is_warning": usage["requests_today"] > 1400
    }