# agent_logic.py
import requests
import json
import streamlit as st
from datetime import datetime
from pathlib import Path
from config import OLLAMA_SYSTEM_PROMPT, GEMINI_ROUTING_PROMPT, LOCATION_NAME, GEMINI_EVENT_PROMPT
from utils import get_weather_info, track_gemini_usage, geocode_location, get_walking_route
import time

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

EVENTS_FILE = Path("events.json")

# --- Ollama Functions ---

def check_ollama():
    try:
        response = requests.get("http://localhost:11434", timeout=2)
        return response.status_code == 200
    except:
        return False

def query_ollama(prompt, model="llama3:latest"):
    """Basic Ollama query without event context"""
    try:
        full_prompt = f"{OLLAMA_SYSTEM_PROMPT}\n\nUser: {prompt}"
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": full_prompt, "stream": False},
            timeout=60
        )
        return r.json().get("response", "No response")
    except Exception as e:
        return f"Error: {str(e)}"

def query_ollama_with_events(prompt, model="llama3:latest"):
    """Ollama query with real event data injected into context"""
    events = load_events_from_file()
    
    # Build event context
    if events and events.get("events"):
        event_list = events["events"]
        event_context = "REAL LOCAL EVENTS (verified from web):\n"
        for i, evt in enumerate(event_list, 1):
            event_context += f"{i}. {evt['name']}\n"
            event_context += f"   Location: {evt.get('location', 'TBD')}\n"
            event_context += f"   Date/Time: {evt.get('date', '')} {evt.get('time', '')}\n"
            event_context += f"   Details: {evt.get('description', 'No details')}\n\n"
        event_context += f"\n(Events last updated: {events.get('last_updated', 'Unknown')})\n"
    else:
        event_context = "NO EVENTS LOADED - Ask user to refresh events in sidebar.\n"
    
    try:
        full_prompt = f"""{OLLAMA_SYSTEM_PROMPT}

{event_context}

User: {prompt}"""
        
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": full_prompt, "stream": False},
            timeout=60
        )
        return r.json().get("response", "No response")
    except Exception as e:
        return f"Error: {str(e)}"

# --- Event Management (Gemini) ---

def fetch_real_events(location, api_key, num_events=5):
    """Use Gemini to fetch real local events from the web"""
    if not GEMINI_AVAILABLE:
        return {"error": "Gemini not available"}
    
    if not api_key:
        return {"error": "No API key provided"}
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        today = datetime.now()
        prompt = f"""{GEMINI_EVENT_PROMPT}

LOCATION: {location}
CURRENT DATE: {today.strftime("%A, %B %d, %Y")}
NUMBER OF EVENTS TO FIND: {num_events}

Search for real events happening in {location} this week and next week.
Return ONLY events you can verify from your search.
"""
        
        response = model.generate_content(prompt)
        
        # Track usage
        track_gemini_usage(response)
        
        text = response.text.strip()
        
        # Extract JSON from response
        start = text.find('[')
        end = text.rfind(']') + 1
        
        if start != -1 and end > start:
            events_list = json.loads(text[start:end])
        else:
            # Try finding object format
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end > start:
                data = json.loads(text[start:end])
                events_list = data.get('events', [])
            else:
                events_list = []
        
        # Geocode each event location
        events_list = geocode_events(events_list[:num_events], location)
        
        return {
            "success": True,
            "events": events_list,
            "last_updated": today.isoformat(),
            "location": location
        }
        
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse events: {str(e)}"}
    except Exception as e:
        return {"error": f"Gemini Error: {str(e)}"}

def geocode_events(events, city):
    """Add lat/lon coordinates to each event"""
    geocoded = []
    for event in events:
        location_str = event.get('location', '')
        if location_str:
            coords = geocode_location(location_str, city)
            if coords:
                event['lat'] = coords['lat']
                event['lon'] = coords['lon']
                event['geocoded'] = True
            else:
                event['geocoded'] = False
            # Rate limit: Nominatim asks for 1 request/second
            time.sleep(1)
        geocoded.append(event)
    return geocoded

def save_events_to_file(events_data):
    """Save events to local JSON file"""
    try:
        with open(EVENTS_FILE, 'w') as f:
            json.dump(events_data, f, indent=2)
        return True
    except Exception as e:
        st.error(f"Failed to save events: {str(e)}")
        return False

def load_events_from_file():
    """Load events from local JSON file"""
    try:
        if EVENTS_FILE.exists():
            with open(EVENTS_FILE, 'r') as f:
                return json.load(f)
        return None
    except Exception as e:
        st.error(f"Failed to load events: {str(e)}")
        return None

def get_events_last_updated():
    """Get timestamp of last event refresh"""
    events = load_events_from_file()
    if events and "last_updated" in events:
        try:
            dt = datetime.fromisoformat(events["last_updated"])
            return dt.strftime("%b %d, %Y %I:%M %p")
        except:
            return events["last_updated"]
    return "Never"

# --- Route Generation (Gemini + OpenRouteService) ---

def generate_gemini_route(route_request, user_location, api_key, ors_api_key=None):
    """Generate route using Gemini for planning + OpenRouteService for real paths"""
    if not GEMINI_AVAILABLE:
        return None
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        weather = get_weather_info(user_location[0], user_location[1])
        now = datetime.now()
        
        # Load real events WITH coordinates
        events = load_events_from_file()
        events_context = ""
        geocoded_events = []
        
        if events and events.get("events"):
            for evt in events["events"]:
                if evt.get("geocoded") and evt.get("lat") and evt.get("lon"):
                    geocoded_events.append(evt)
            
            events_context = "VERIFIED LOCAL EVENTS WITH COORDINATES:\n"
            for evt in geocoded_events:
                events_context += f"- {evt['name']} at {evt.get('location', 'unknown')}\n"
                events_context += f"  Coordinates: [{evt['lat']}, {evt['lon']}]\n"
                events_context += f"  Date/Time: {evt.get('date', 'TBD')} {evt.get('time', '')}\n\n"
        
        prompt = f"""{GEMINI_ROUTING_PROMPT}
        
ROUTE REQUEST: {json.dumps(route_request)}
CONTEXT: {now.strftime("%A %I:%M %p")}, Weather: {weather['condition']}
LOCATION: {LOCATION_NAME}
USER START LOCATION: {user_location[0]}, {user_location[1]}

{events_context}

IMPORTANT: 
- Use the EXACT coordinates provided for events
- Start from the user's location: [{user_location[0]}, {user_location[1]}]
- Include waypoints that pass by the relevant event locations
- Return waypoints in [lat, lon] format
"""
        
        response = model.generate_content(prompt)
        
        # Track usage
        track_gemini_usage(response)
        
        text = response.text.strip()
        
        # Extract JSON
        start = text.find('{')
        end = text.rfind('}') + 1
        route_data = json.loads(text[start:end])
        route_data['weather'] = weather
        
        # If we have ORS API key, get real walking route
        if ors_api_key and route_data.get('waypoints'):
            real_route = get_real_walking_route(route_data['waypoints'], ors_api_key)
            if real_route:
                route_data['waypoints'] = real_route['coordinates']
                route_data['real_distance'] = f"{real_route['distance_miles']} miles"
                route_data['real_duration'] = f"{real_route['duration_minutes']} minutes"
                route_data['route_type'] = 'road-following'
            else:
                route_data['route_type'] = 'straight-line (ORS failed)'
        else:
            route_data['route_type'] = 'straight-line (no ORS key)'
        
        return route_data
    except Exception as e:
        st.error(f"Gemini Error: {str(e)}")
        return None

def get_real_walking_route(waypoints, ors_api_key):
    """Convert waypoints to real walking route using OpenRouteService"""
    if not waypoints or len(waypoints) < 2:
        return None
    
    try:
        # Convert [lat, lon] to [lon, lat] for ORS
        ors_coords = [[wp[1], wp[0]] for wp in waypoints]
        
        return get_walking_route(ors_coords, ors_api_key)
    except Exception as e:
        print(f"Real route error: {str(e)}")
        return None