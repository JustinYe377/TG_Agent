# agent_logic.py
import requests
import json
import streamlit as st
from datetime import datetime
from pathlib import Path
from config import OLLAMA_SYSTEM_PROMPT, GEMINI_ROUTING_PROMPT, LOCATION_NAME, GEMINI_EVENT_PROMPT
from utils import get_weather_info, track_gemini_usage

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
        
        return {
            "success": True,
            "events": events_list[:num_events],
            "last_updated": today.isoformat(),
            "location": location
        }
        
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse events: {str(e)}"}
    except Exception as e:
        return {"error": f"Gemini Error: {str(e)}"}

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

# --- Route Generation (Gemini) ---

def generate_gemini_route(route_request, user_location, api_key):
    """Generate route using Gemini with real event data"""
    if not GEMINI_AVAILABLE:
        return None
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        weather = get_weather_info(user_location[0], user_location[1])
        now = datetime.now()
        
        # Load real events
        events = load_events_from_file()
        events_context = ""
        if events and events.get("events"):
            events_context = f"VERIFIED LOCAL EVENTS:\n{json.dumps(events['events'], indent=2)}"
        
        prompt = f"""{GEMINI_ROUTING_PROMPT}
        
ROUTE REQUEST: {json.dumps(route_request)}
CONTEXT: {now.strftime("%A %I:%M %p")}, Weather: {weather['condition']}
LOCATION: {LOCATION_NAME}

{events_context}

Use the verified events above when planning the route. Only reference events from this list.
"""
        
        response = model.generate_content(prompt)
        
        # Track usage
        track_gemini_usage(response)
        
        text = response.text.strip()
        
        # Simple JSON extraction
        start = text.find('{')
        end = text.rfind('}') + 1
        route_data = json.loads(text[start:end])
        route_data['weather'] = weather
        return route_data
    except Exception as e:
        st.error(f"Gemini Error: {str(e)}")
        return None