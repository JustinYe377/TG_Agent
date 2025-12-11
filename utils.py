# utils.py
import requests
import re
import json
import streamlit as st
from datetime import datetime, date

def extract_route_request(text):
    """Extract route request details from Ollama response"""
    pattern = r'\[ROUTE_REQUEST\](.*?)\[/ROUTE_REQUEST\]'
    match = re.search(pattern, text, re.DOTALL)
    
    if match:
        content = match.group(1)
        request = {}
        for line in content.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                request[key.strip().lower()] = value.strip()
        return request
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