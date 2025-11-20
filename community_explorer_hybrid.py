import streamlit as st
import requests
import json
import folium
from streamlit_folium import st_folium
from datetime import datetime
import re
from typing import List, Dict, Optional, Any

# Optional Gemini import
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# ===============================================================================
# CONFIGURATION
# ===============================================================================

st.set_page_config(page_title="Local Community Explorer", layout="wide")

# Default location (Athens, OH)
DEFAULT_LAT = 39.3292
DEFAULT_LON = -82.1013
LOCATION_NAME = "Athens, Ohio"

# ===============================================================================
# INTENT DETECTION
# ===============================================================================

def detect_intent(user_message):
    """
    Fast keyword-based intent detection
    Returns: ("ROUTE_PLANNING" | "EVENT_SEARCH" | "CASUAL_CHAT", confidence_score)
    """
    message_lower = user_message.lower()
    
    # Route planning keywords
    route_keywords = [
        'route', 'walk', 'bike', 'hike', 'path', 'direction', 'directions',
        'go to', 'take me', 'show me', 'find', 'explore', 'get to',
        'bored', 'something to do', 'what should i do', 'where should',
        'trail', 'outdoor', 'outside', 'exercise', 'jog', 'run'
    ]
    
    # Event search keywords
    event_keywords = [
        'event', 'happening', 'tonight', 'today', 'this week', 'weekend',
        'concert', 'festival', 'market', 'farmers market', 'live music',
        'activities', 'what\'s going on', 'things to do', 'open now'
    ]
    
    # Count matches
    route_score = sum(1 for kw in route_keywords if kw in message_lower)
    event_score = sum(1 for kw in event_keywords if kw in message_lower)
    
    # Determine intent
    if route_score > 0 or event_score > 0:
        if route_score >= event_score:
            confidence = min(0.9, 0.5 + (route_score * 0.15))
            return "ROUTE_PLANNING", confidence
        else:
            confidence = min(0.9, 0.5 + (event_score * 0.15))
            return "EVENT_SEARCH", confidence
    
    # Default to casual chat
    return "CASUAL_CHAT", 0.9


# ===============================================================================
# GEMINI FUNCTION DEFINITIONS
# ===============================================================================

def get_function_declarations():
    """Define functions that Gemini can call - using Python functions directly"""
    # Import genai if available to use proper types
    try:
        import google.generativeai as genai
    except ImportError:
        # Fallback to basic dict format
        pass
    
    # Define tools as Python functions for Gemini
    tools = [
        generate_walking_route,
        find_local_events,
        get_weather_and_conditions
    ]
    
    return tools


# ===============================================================================
# FUNCTION IMPLEMENTATIONS
# ===============================================================================

def get_weather_and_conditions(include_forecast: bool = False) -> Dict[str, Any]:
    """
    Gets current weather conditions and forecast for outdoor activities in Athens, Ohio.
    
    Args:
        include_forecast: Whether to include forecast for next few hours
    
    Returns:
        Dictionary with weather information including temperature, condition, wind speed, and suitability for walking
    """
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={DEFAULT_LAT}&longitude={DEFAULT_LON}&current=temperature_2m,weathercode,windspeed_10m&temperature_unit=fahrenheit"
        response = requests.get(url, timeout=5)
        data = response.json()
        
        current = data.get('current', {})
        temp = current.get('temperature_2m', 'N/A')
        wind = current.get('windspeed_10m', 'N/A')
        
        weather_codes = {
            0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
            45: "Foggy", 48: "Foggy", 51: "Light Drizzle", 53: "Drizzle",
            55: "Heavy Drizzle", 61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
            71: "Light Snow", 73: "Snow", 75: "Heavy Snow"
        }
        
        code = current.get('weathercode', 0)
        condition = weather_codes.get(code, "Unknown")
        
        return {
            "temperature": f"{temp}°F",
            "condition": condition,
            "wind_speed": f"{wind} mph",
            "suitable_for_walking": code < 60,  # Good if not raining/snowing
            "summary": f"{temp}°F and {condition}, winds {wind} mph"
        }
    except Exception as e:
        return {
            "temperature": "N/A",
            "condition": "Unable to fetch",
            "wind_speed": "N/A",
            "suitable_for_walking": True,
            "summary": "Weather data unavailable"
        }


def find_local_events(time_frame: str = "today", event_types: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Finds current and upcoming local events, markets, concerts, and activities in Athens, Ohio.
    
    Args:
        time_frame: When to search - now, today, tonight, this_week, or weekend
        event_types: Types of events - market, concert, festival, sports, art, food, or social
    
    Returns:
        Dictionary with event information including name, location, time, and description
    """
    now = datetime.now()
    day_of_week = now.strftime("%A")
    hour = now.hour
    
    # Simulate typical Athens, OH events based on day/time
    events = []
    
    # Saturday Farmers Market
    if day_of_week == "Saturday" and 7 <= hour <= 13:
        events.append({
            "name": "Athens Farmers Market",
            "location": "Riverfront Park (1 Depot St)",
            "time": "9:00 AM - 1:00 PM",
            "description": "Local vendors, fresh produce, crafts, and live music",
            "type": "market",
            "happening_now": True,
            "coordinates": [39.3350, -82.0980]
        })
    
    # Weeknight events
    if day_of_week in ["Thursday", "Friday", "Saturday"] and hour >= 17:
        events.append({
            "name": "Live Music at The Union",
            "location": "The Union Bar & Grill (18 W Union St)",
            "time": "7:00 PM - 10:00 PM",
            "description": "Local bands and open mic night",
            "type": "concert",
            "happening_now": hour >= 19,
            "coordinates": [39.3285, -82.1015]
        })
    
    # Coffee shop gatherings (daily)
    if 7 <= hour <= 20:
        events.append({
            "name": "Coffee Shop Social Scene",
            "location": "Donkey Coffee (17 W Washington St)",
            "time": "Open 7 AM - 8 PM",
            "description": "Popular spot for locals, students, and remote workers",
            "type": "social",
            "happening_now": True,
            "coordinates": [39.3292, -82.1018]
        })
    
    # Weekend events
    if day_of_week in ["Saturday", "Sunday"] and 10 <= hour <= 18:
        events.append({
            "name": "Strouds Run State Park",
            "location": "11661 State Park Rd",
            "time": "Dawn to Dusk",
            "description": "Hiking trails, lake views, perfect for outdoor activities",
            "type": "outdoor",
            "happening_now": True,
            "coordinates": [39.3920, -82.0420]
        })
    
    # Add campus events on weekdays
    if day_of_week not in ["Saturday", "Sunday"] and 10 <= hour <= 16:
        events.append({
            "name": "Ohio University Campus Activities",
            "location": "College Green",
            "time": "Various throughout day",
            "description": "Student organizations, outdoor activities, food trucks",
            "type": "campus",
            "happening_now": True,
            "coordinates": [39.3248, -82.1012]
        })
    
    return {
        "events": events,
        "count": len(events),
        "time_frame": time_frame,
        "searched_at": now.strftime("%I:%M %p")
    }


def generate_walking_route(route_type: str = "walking", 
                          destination_hint: str = "downtown", 
                          preferences: Optional[List[str]] = None, 
                          distance_preference: str = "medium") -> Dict[str, Any]:
    """
    Generates a detailed walking route with waypoints, events, and social opportunities in Athens, Ohio.
    
    Args:
        route_type: Type of route - walking, scenic, exercise, or social
        destination_hint: General destination area - river, downtown, campus, uptown, parks, or trails
        preferences: User preferences - events, quiet, busy, nature, urban, social
        distance_preference: Preferred distance - short (under 1 mile), medium (1-3 miles), or long (3+ miles)
    
    Returns:
        Dictionary with route information including waypoints, distance, time, and points of interest
    """
    preferences = preferences or []
    
    # Base waypoints for different destinations
    route_templates = {
        "river": [
            [DEFAULT_LAT, DEFAULT_LON],  # Start (downtown)
            [39.3310, -82.1005],  # Towards river
            [39.3350, -82.0980],  # Riverfront Park
            [39.3360, -82.0965],  # Along river trail
            [39.3340, -82.0990]   # Return loop
        ],
        "downtown": [
            [DEFAULT_LAT, DEFAULT_LON],  # Start
            [39.3285, -82.1015],  # Union St
            [39.3270, -82.1020],  # Court St
            [39.3280, -82.1005],  # Stimson Ave
            [39.3292, -82.1013]   # Back to start
        ],
        "campus": [
            [DEFAULT_LAT, DEFAULT_LON],  # Start (downtown)
            [39.3268, -82.1010],  # Towards campus
            [39.3248, -82.1012],  # College Green
            [39.3230, -82.1015],  # South Green
            [39.3260, -82.1000]   # Campus edge
        ],
        "uptown": [
            [DEFAULT_LAT, DEFAULT_LON],  # Start
            [39.3300, -82.1000],  # Court St uptown
            [39.3315, -82.0995],  # Uptown shops
            [39.3320, -82.1010],  # East State St
            [39.3305, -82.1015]   # Loop back
        ],
        "parks": [
            [DEFAULT_LAT, DEFAULT_LON],  # Start
            [39.3310, -82.1030],  # Towards park
            [39.3330, -82.1040],  # City Park
            [39.3340, -82.1025],  # Through park
            [39.3320, -82.1010]   # Exit park
        ]
    }
    
    # Select route based on destination hint
    waypoints = route_templates.get(destination_hint.lower(), route_templates["downtown"])
    
    # Adjust route length based on preference
    if distance_preference == "short":
        waypoints = waypoints[:3]
    elif distance_preference == "long":
        # Add extra waypoints
        waypoints = waypoints + [[waypoints[-1][0] + 0.005, waypoints[-1][1] - 0.005]]
    
    # Calculate distance (rough approximation)
    total_distance = len(waypoints) * 0.3  # ~0.3 miles per waypoint
    estimated_time = int(total_distance * 20)  # ~20 min per mile
    
    # Generate points of interest based on route
    pois = []
    if "social" in preferences or "events" in preferences:
        pois.extend(["Coffee shops along Court St", "Farmers Market area", "Campus gathering spots"])
    if "nature" in preferences or route_type == "scenic":
        pois.extend(["Hocking River views", "Tree-lined streets", "City parks"])
    if "urban" in preferences:
        pois.extend(["Local shops", "Restaurants", "Art galleries"])
    
    return {
        "waypoints": waypoints,
        "total_distance": f"{total_distance:.1f} miles",
        "estimated_time": f"{estimated_time} minutes",
        "route_type": route_type,
        "destination": destination_hint,
        "points_of_interest": pois[:5],  # Limit to 5
        "surface_types": ["paved sidewalks", "some brick paths"],
        "accessibility": "Wheelchair accessible on main streets",
        "best_for": preferences
    }


def execute_function_call(function_name, function_args):
    """Execute the called function and return results"""
    if function_name == "generate_walking_route":
        return generate_walking_route(**function_args)
    elif function_name == "find_local_events":
        return find_local_events(**function_args)
    elif function_name == "get_weather_and_conditions":
        return get_weather_and_conditions(**function_args)
    else:
        return {"error": f"Unknown function: {function_name}"}


def extract_function_args(fc_args):
    """
    Safely extract function arguments from Gemini's function call response.
    Handles protobuf Struct format.
    """
    if not fc_args:
        return {}
    
    function_args = {}
    
    try:
        # Method 1: Try to iterate over keys (works with protobuf Struct)
        for key in fc_args:
            value = fc_args[key]
            
            # Handle different value types in protobuf
            if isinstance(value, str):
                function_args[key] = value
            elif isinstance(value, (int, float, bool)):
                function_args[key] = value
            elif isinstance(value, list):
                function_args[key] = value
            elif hasattr(value, 'string_value'):
                function_args[key] = value.string_value
            elif hasattr(value, 'number_value'):
                function_args[key] = value.number_value
            elif hasattr(value, 'bool_value'):
                function_args[key] = value.bool_value
            elif hasattr(value, 'list_value'):
                # Handle list values
                list_items = []
                if hasattr(value.list_value, 'values'):
                    for item in value.list_value.values:
                        if hasattr(item, 'string_value'):
                            list_items.append(item.string_value)
                        elif hasattr(item, 'number_value'):
                            list_items.append(item.number_value)
                        else:
                            list_items.append(str(item))
                function_args[key] = list_items
            else:
                # Last resort: convert to string
                function_args[key] = str(value)
    except Exception as e:
        # If all else fails, try to convert the whole thing
        try:
            function_args = dict(fc_args)
        except:
            # Give up and return empty dict
            st.warning(f"Could not extract function arguments: {e}")
            return {}
    
    return function_args


# ===============================================================================
# OLLAMA INTEGRATION
# ===============================================================================

def has_ollama():
    """Check if Ollama is running locally"""
    try:
        response = requests.get("http://localhost:11434", timeout=2)
        return response.status_code == 200
    except:
        return False


def ollama_chat(prompt, system_prompt=None, model="llama3.2:latest"):
    """Query local Ollama for casual chat or narration"""
    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        r = requests.post(
            "http://localhost:11434/api/chat",
            json={"model": model, "messages": messages, "stream": True},
            stream=True,
            timeout=60
        )
        
        full_response = ""
        for line in r.iter_lines():
            if not line:
                continue
            try:
                j = json.loads(line.decode("utf-8"))
                if "message" in j and "content" in j["message"]:
                    full_response += j["message"]["content"]
                if j.get("done", False):
                    break
            except json.JSONDecodeError:
                continue
        
        return full_response.strip() if full_response else "No response received"
    except Exception as e:
        return f"Error querying Ollama: {str(e)}"


OLLAMA_NARRATOR_PROMPT = f"""You are an enthusiastic community connector for {LOCATION_NAME}. 

Your job is to take STRUCTURED DATA about routes and events, and turn it into EXCITING, ACTIONABLE messages that get people outside.

YOUR PERSONALITY:
- Enthusiastic and pushy (in a friendly way)
- Focused on getting people to act NOW
- Highlight the most exciting/time-sensitive opportunities
- Use emojis sparingly but effectively
- Keep it concise but compelling

RULES:
1. Don't just list information - tell a story about their adventure
2. Always emphasize what's happening NOW or SOON
3. Be specific about times, distances, locations
4. End with a clear call to action
5. Never be passive - be the friend who drags you off the couch

Example:
Bad: "There are some events happening. The route is 2 miles."
Good: "Perfect timing! There's a farmers market happening RIGHT NOW (9am-1pm) at Riverfront Park, and I've mapped you a scenic 2-mile route that passes right by it. It's 65° and sunny - literally perfect. Let's go! 🌞"
"""


# ===============================================================================
# GEMINI + OLLAMA ORCHESTRATION
# ===============================================================================

def process_with_hybrid_system(user_message, api_key):
    """
    Main orchestration: Gemini for planning, Ollama for narration
    """
    # Step 1: Detect intent
    intent, confidence = detect_intent(user_message)
    
    if intent == "CASUAL_CHAT":
        # Route directly to Ollama for casual conversation
        response = ollama_chat(
            user_message,
            system_prompt=f"You are a friendly local guide for {LOCATION_NAME}. Be helpful, casual, and encouraging."
        )
        return {
            "type": "casual_chat",
            "response": response,
            "used_gemini": False
        }
    
    # Step 2: Use Gemini function calling for planning
    if not GEMINI_AVAILABLE:
        return {
            "type": "error",
            "response": "Gemini is not available. Please install: pip install google-generativeai"
        }
    
    try:
        genai.configure(api_key=api_key)
        
        # Get current context
        now = datetime.now()
        weather = get_weather_and_conditions()
        
        # Create Gemini model with function calling
        try:
            model = genai.GenerativeModel(
                'gemini-2.0-flash-exp',
                tools=get_function_declarations()
            )
        except Exception as e:
            # Fallback to non-experimental model
            model = genai.GenerativeModel(
                'gemini-1.5-flash',
                tools=get_function_declarations()
            )
        
        # Enhanced prompt with context
        context_prompt = f"""Current context:
- Location: {LOCATION_NAME}
- Time: {now.strftime('%A, %I:%M %p')}
- Weather: {weather['summary']}

User request: {user_message}

Generate a route and/or find events that get this person engaged with the community TODAY."""
        
        # Step 3: Gemini decides what functions to call
        response = model.generate_content(context_prompt)
        
        # Step 4: Execute function calls
        function_results = {}
        route_data = None
        events_data = None
        
        # Debug: Show response structure
        try:
            if not response.candidates:
                st.error("No candidates in Gemini response")
                return {
                    "type": "error",
                    "response": "Gemini returned no candidates. Please try again.",
                    "used_gemini": True
                }
            
            candidate = response.candidates[0]
            
            if not hasattr(candidate, 'content') or not candidate.content:
                st.error("No content in candidate")
                return {
                    "type": "error", 
                    "response": "Gemini returned empty content. Please try rephrasing your request.",
                    "used_gemini": True
                }
            
            if not candidate.content.parts:
                st.error("No parts in content")
                # Gemini might have just returned text
                if hasattr(response, 'text') and response.text:
                    return {
                        "type": "gemini_response",
                        "response": response.text,
                        "used_gemini": True
                    }
            
            # Process each part
            for idx, part in enumerate(candidate.content.parts):
                # Check if this part is a function call
                if hasattr(part, 'function_call') and part.function_call:
                    fc = part.function_call
                    function_name = fc.name
                    
                    st.info(f"🔧 Executing function: {function_name}")
                    
                    # Extract function arguments using helper
                    function_args = extract_function_args(fc.args if hasattr(fc, 'args') else None)
                    
                    # Debug: show what we're calling
                    with st.expander(f"🔍 Debug: Function Call {idx + 1}"):
                        st.write(f"**Function:** {function_name}")
                        st.write(f"**Arguments:** {function_args}")
                    
                    # Execute the function
                    try:
                        result = execute_function_call(function_name, function_args)
                        function_results[function_name] = result
                        
                        # Store for map rendering
                        if function_name == "generate_walking_route":
                            route_data = result
                        elif function_name == "find_local_events":
                            events_data = result
                        
                        st.success(f"✅ {function_name} completed")
                    except Exception as e:
                        st.error(f"Error executing {function_name}: {e}")
                        function_results[function_name] = {"error": str(e)}
        except Exception as e:
            st.warning(f"Error processing Gemini response: {e}")
            # Continue with empty function_results
            pass
        
        # Step 5: Hand off to Ollama for friendly narration
        if function_results:
            narration_prompt = f"""The user said: "{user_message}"

We gathered this information:

{json.dumps(function_results, indent=2)}

Write an ENTHUSIASTIC message that:
1. Confirms what they're looking for
2. Highlights the BEST/MOST URGENT opportunities
3. Gives specific details (times, distances, locations)
4. Pushes them to act NOW
5. Keeps it under 150 words

Remember: Your goal is to get them excited and OUT THE DOOR!"""
            
            narration = ollama_chat(narration_prompt, system_prompt=OLLAMA_NARRATOR_PROMPT)
            
            return {
                "type": "route_planning",
                "response": narration,
                "route_data": route_data,
                "events_data": events_data,
                "weather_data": weather,
                "function_results": function_results,
                "used_gemini": True
            }
        else:
            # Gemini didn't call functions, just responded with text
            gemini_text = response.text if response.text else "I couldn't generate a route for that request."
            return {
                "type": "gemini_response",
                "response": gemini_text,
                "used_gemini": True
            }
    
    except Exception as e:
        error_msg = f"Error in hybrid system: {str(e)}"
        st.error(error_msg)
        
        # Show detailed error info for debugging
        with st.expander("🐛 Error Details (for debugging)"):
            st.code(error_msg)
            import traceback
            st.code(traceback.format_exc())
            st.write("**Tip:** Check if your Gemini API key is valid and has available quota")
        
        # Fallback: try to use Ollama for a helpful response
        try:
            fallback_response = ollama_chat(
                user_message,
                system_prompt=f"The route planning system is having issues. Provide a helpful, friendly response about {LOCATION_NAME} and suggest the user try again in a moment."
            )
            
            return {
                "type": "error_with_fallback",
                "response": f"⚠️ Having trouble with route planning right now.\n\n{fallback_response}",
                "error": str(e),
                "used_gemini": False
            }
        except:
            # If even Ollama fails, return basic error
            return {
                "type": "error",
                "response": f"Error in hybrid system: {str(e)}\n\nPlease check that Ollama is running and your Gemini API key is valid.",
                "used_gemini": False
            }


# ===============================================================================
# MAP RENDERING
# ===============================================================================

def create_map(center, routes, route_details):
    """Create Folium map with routes and detailed markers"""
    m = folium.Map(location=center, zoom_start=14, tiles='OpenStreetMap')
    
    colors = ['blue', 'red', 'green', 'purple', 'orange']
    
    if not routes:
        folium.Marker(
            center,
            popup="Your Location",
            icon=folium.Icon(color='blue', icon='home')
        ).add_to(m)
        return m
    
    for idx, (route, details) in enumerate(zip(routes, route_details)):
        color = colors[idx % len(colors)]
        
        if len(route) >= 2:
            # Draw route line
            folium.PolyLine(
                route, 
                weight=5, 
                color=color,
                opacity=0.8,
                popup=f"Route {idx + 1}"
            ).add_to(m)
            
            # Start marker
            folium.Marker(
                route[0], 
                popup=f"<b>Start</b>",
                icon=folium.Icon(color='green', icon='play')
            ).add_to(m)
            
            # End marker
            folium.Marker(
                route[-1], 
                popup=f"<b>End</b>",
                icon=folium.Icon(color='red', icon='stop')
            ).add_to(m)
            
            # POI markers
            if 'points_of_interest' in details and isinstance(details['points_of_interest'], list):
                poi_count = min(len(details['points_of_interest']), len(route) - 2)
                step = max(1, (len(route) - 2) // poi_count) if poi_count > 0 else 1
                
                for i, poi in enumerate(details['points_of_interest'][:poi_count]):
                    if (i + 1) * step < len(route):
                        folium.Marker(
                            route[(i + 1) * step],
                            popup=f"📍 {poi}",
                            icon=folium.Icon(color='lightblue', icon='info-sign')
                        ).add_to(m)
            
            # Event markers
            if 'events' in details:
                for event in details['events']:
                    if 'coordinates' in event:
                        folium.Marker(
                            event['coordinates'],
                            popup=f"🎉 <b>{event['name']}</b><br>{event['time']}",
                            icon=folium.Icon(color='orange', icon='star')
                        ).add_to(m)
    
    return m


# ===============================================================================
# STREAMLIT UI
# ===============================================================================

# Initialize session state
if "routes" not in st.session_state:
    st.session_state.routes = []
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "gemini_api_key" not in st.session_state:
    st.session_state.gemini_api_key = ""
if "map_center" not in st.session_state:
    st.session_state.map_center = [DEFAULT_LAT, DEFAULT_LON]
if "route_details" not in st.session_state:
    st.session_state.route_details = []

# Sidebar
with st.sidebar:
    st.title("⚙️ Configuration")
    
    # System status
    ollama_status = has_ollama()
    st.write("**🤖 AI Systems:**")
    st.write("Ollama (Chat):", "🟢 Connected" if ollama_status else "🔴 Not Connected")
    
    if not ollama_status:
        st.warning("Start Ollama with: `ollama serve`")
        st.info("Ollama handles casual chat (FREE). Gemini handles route planning (paid).")
    
    # Gemini API Key
    st.write("**Gemini API Key:**")
    api_key = st.text_input(
        "Enter API Key", 
        value=st.session_state.gemini_api_key,
        type="password",
        help="Get your API key from https://aistudio.google.com/apikey"
    )
    if api_key:
        st.session_state.gemini_api_key = api_key
        if GEMINI_AVAILABLE:
            st.success("✅ Gemini ready (route planning)")
    
    st.divider()
    
    # Location
    st.subheader("📍 Your Location")
    st.write(f"**{LOCATION_NAME}**")
    st.write(f"Lat: {DEFAULT_LAT}, Lon: {DEFAULT_LON}")
    
    # Weather
    weather = get_weather_and_conditions()
    st.write("**Current Weather:**")
    st.write(f"🌡️ {weather['temperature']}")
    st.write(f"☁️ {weather['condition']}")
    st.write(f"💨 {weather['wind_speed']}")
    
    st.divider()
    
    # Cost info
    with st.expander("💰 How the hybrid system works"):
        st.markdown("""
        **Casual Chat** (FREE)
        - Uses Ollama (local)
        - Weather questions, greetings, general info
        
        **Route Planning** (Paid)
        - Uses Gemini function calling
        - Route generation, event search
        - ~$0.001 per request
        
        **Typical Usage:**
        - 80% free (Ollama chat)
        - 20% paid (Gemini planning)
        """)
    
    # Map controls
    st.subheader("🗺️ Map Controls")
    if st.button("Clear All Routes", use_container_width=True):
        st.session_state.routes = []
        st.session_state.route_details = []
        st.rerun()

# Main UI
st.title("🏘️ Local Community Explorer")
st.markdown("*Hybrid AI: Gemini plans routes, Ollama adds personality*")

# Create tabs
tab1, tab2 = st.tabs(["💬 AI Assistant", "🗺️ Map View"])

# Tab 1: Chat Interface
with tab1:
    st.subheader("Chat with Your Local Guide")
    
    # Example prompts
    with st.expander("💡 Try These Examples"):
        st.markdown("""
        **Route Planning (Gemini):**
        - "I'm bored, what's happening?"
        - "Want to walk by the river"
        - "Find me something to do tonight"
        
        **Casual Chat (Ollama - FREE):**
        - "What's the weather like?"
        - "Tell me about Athens"
        - "Any good coffee shops?"
        """)
    
    # Display chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "metadata" in msg and msg["metadata"].get("used_gemini"):
                st.caption("🔵 Powered by Gemini + Ollama")
            elif "metadata" in msg:
                st.caption("🟢 Powered by Ollama (FREE)")
    
    # Chat input
    if prompt := st.chat_input("Ask for routes or chat casually..."):
        # Add user message
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.write(prompt)
        
        # Process with hybrid system
        with st.chat_message("assistant"):
            if not ollama_status:
                error_msg = "⚠️ Ollama is not connected. Please start Ollama to use this app."
                st.error(error_msg)
                st.session_state.chat_history.append({
                    "role": "assistant", 
                    "content": error_msg,
                    "metadata": {"used_gemini": False}
                })
            elif not st.session_state.gemini_api_key:
                error_msg = "⚠️ Please enter your Gemini API key in the sidebar for route planning. Casual chat still works!"
                st.warning(error_msg)
                # Still process with Ollama only
                result = process_with_hybrid_system(prompt, "")
                st.write(result['response'])
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": result['response'],
                    "metadata": {"used_gemini": False}
                })
            else:
                with st.spinner("🤔 Processing..."):
                    # Detect intent first (show to user)
                    intent, confidence = detect_intent(prompt)
                    
                    if intent == "CASUAL_CHAT":
                        st.caption(f"💬 Routing to Ollama (casual chat)")
                    else:
                        st.caption(f"🎯 Routing to Gemini (planning) + Ollama (narration)")
                    
                    # Process request
                    result = process_with_hybrid_system(prompt, st.session_state.gemini_api_key)
                    
                    # Display response
                    st.write(result['response'])
                    
                    # If route was generated, add to map
                    if result['type'] == 'route_planning' and result.get('route_data'):
                        route_data = result['route_data']
                        events_data = result.get('events_data')
                        
                        # Add route to session state
                        waypoints = route_data.get('waypoints', [])
                        if len(waypoints) >= 2:
                            st.session_state.routes.append(waypoints)
                            
                            details = {
                                'points_of_interest': route_data.get('points_of_interest', []),
                                'events': events_data.get('events', []) if events_data else []
                            }
                            st.session_state.route_details.append(details)
                            st.session_state.map_center = waypoints[0]
                            
                            # Show quick summary
                            with st.expander("📊 Route Details"):
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Distance", route_data.get('total_distance', 'N/A'))
                                with col2:
                                    st.metric("Time", route_data.get('estimated_time', 'N/A'))
                                with col3:
                                    st.metric("Events", len(details['events']))
                                
                                if details['events']:
                                    st.write("**📅 Events Along Route:**")
                                    for event in details['events']:
                                        st.write(f"• **{event['name']}** - {event['time']}")
                                        if event.get('happening_now'):
                                            st.write("  🔴 **HAPPENING NOW!**")
                            
                            st.success("✅ Route added to map! Check the Map View tab.")
                    
                    # Save to history
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": result['response'],
                        "metadata": {
                            "used_gemini": result.get('used_gemini', False),
                            "type": result['type']
                        }
                    })

# Tab 2: Map View
with tab2:
    st.subheader("Interactive Route Map")
    
    if st.session_state.routes:
        st.write(f"**Active Routes:** {len(st.session_state.routes)}")
        
        for idx in range(len(st.session_state.routes)):
            with st.expander(f"Route {idx + 1} Details"):
                details = st.session_state.route_details[idx] if idx < len(st.session_state.route_details) else {}
                st.write(f"**Waypoints:** {len(st.session_state.routes[idx])}")
                
                if details.get('events'):
                    st.write("**Events:**")
                    for event in details['events']:
                        st.write(f"  • {event['name']} - {event['location']}")
                
                if st.button(f"🗑️ Remove Route {idx + 1}", key=f"remove_{idx}"):
                    st.session_state.routes.pop(idx)
                    if idx < len(st.session_state.route_details):
                        st.session_state.route_details.pop(idx)
                    st.rerun()
    else:
        st.info("No routes yet. Ask the AI assistant to create one!")
    
    # Render map
    m = create_map(st.session_state.map_center, st.session_state.routes, st.session_state.route_details)
    st_folium(m, width=None, height=600, key="main_map")

# Footer
st.divider()
col1, col2, col3 = st.columns(3)
with col1:
    st.caption(f"📍 {LOCATION_NAME}")
with col2:
    st.caption(f"🗺️ Routes: {len(st.session_state.routes)}")
with col3:
    st.caption(f"💬 Messages: {len(st.session_state.chat_history)}")