import streamlit as st
import requests
import json
import folium
from streamlit_folium import st_folium
from datetime import datetime
import re

# Optional Gemini import
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# ------------------- CONFIG -------------------
st.set_page_config(page_title="Local Community Explorer", layout="wide")

# Default location (Athens, OH)
DEFAULT_LAT = 39.3292
DEFAULT_LON = -82.1013
LOCATION_NAME = "Athens, Ohio"

# ------------------- SYSTEM PROMPTS -------------------
OLLAMA_SYSTEM_PROMPT = f"""You are a local community assistant for {LOCATION_NAME}.

YOUR ROLE:
1. Understand user's route/exploration requests
2. Extract key details: destination type, preferences, starting point
3. Ask clarifying questions if needed
4. Format route requests for the mapping system

WHEN USER ASKS FOR ROUTES:
- Identify the route type (walking, biking, driving)
- Determine key landmarks or destination types (river, park, downtown, etc.)
- Note any preferences (scenic, short, accessible, etc.)
- Extract or confirm starting location

RESPONSE FORMAT FOR ROUTE REQUESTS:
When you determine the user wants a route, respond with:
[ROUTE_REQUEST]
Type: [walking/biking/driving]
From: [starting location or coordinates]
To: [destination or area type]
Preferences: [any special requirements]
Description: [Brief description of what user wants]
[/ROUTE_REQUEST]

For general questions, provide helpful local information about {LOCATION_NAME}.

Current location context: {LOCATION_NAME} is a college town with Ohio University, Hocking River runs through it, has uptown area, many parks and hiking trails nearby."""

GEMINI_ROUTING_PROMPT = """You are a precise mapping and routing assistant.

YOUR ROLE:
1. Generate realistic walking/biking/driving routes based on requests
2. Provide waypoints that follow actual paths (roads, trails, sidewalks)
3. Include detailed route descriptions
4. Consider weather and conditions

INPUT FORMAT:
You will receive route requests with:
- Route type (walking/biking/driving)
- Start location (coordinates or description)
- Destination (coordinates or description)
- User preferences

OUTPUT FORMAT (JSON):
{
  "waypoints": [[lat, lon], [lat, lon], ...],
  "route_description": "Detailed turn-by-turn description",
  "total_distance": "X.X miles/km",
  "estimated_time": "XX minutes",
  "points_of_interest": ["landmark 1", "landmark 2"],
  "surface_types": ["paved", "gravel", "trail"],
  "accessibility": "wheelchair accessible / moderate difficulty / challenging",
  "weather_considerations": "Current conditions and recommendations",
  "best_times": "Recommended times to take this route"
}

IMPORTANT:
- Generate 5-15 waypoints that create a realistic path
- For river routes, follow the riverbank
- For scenic routes, include parks and viewpoints
- Consider actual geography of the area
- Provide practical, safe routing"""

# ------------------- STATE INITIALIZATION -------------------
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
if "processing" not in st.session_state:
    st.session_state.processing = False

# ------------------- HELPER FUNCTIONS -------------------
def has_ollama():
    """Check if Ollama is running locally"""
    try:
        response = requests.get("http://localhost:11434", timeout=2)
        return response.status_code == 200
    except:
        return False

def ollama_query(prompt, model="llama3:latest", system_prompt=None):
    """Query local Ollama instance with system prompt"""
    try:
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\nUser: {prompt}"
        
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": full_prompt, "stream": True},
            stream=True,
            timeout=60
        )
        
        full_response = ""
        for line in r.iter_lines():
            if not line:
                continue
            try:
                j = json.loads(line.decode("utf-8"))
                if "response" in j:
                    full_response += j["response"]
                if j.get("done", False):
                    break
            except json.JSONDecodeError:
                continue
        
        return full_response.strip() if full_response else "No response received"
    except Exception as e:
        return f"Error querying Ollama: {str(e)}"

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
    """Get current weather information (using Open-Meteo free API)"""
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weathercode,windspeed_10m&temperature_unit=fahrenheit"
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
            "wind_speed": f"{wind} mph"
        }
    except Exception as e:
        return {
            "temperature": "N/A",
            "condition": "Unable to fetch",
            "wind_speed": "N/A"
        }

def gemini_generate_route(route_request, user_location, api_key):
    """Generate detailed route using Gemini API"""
    if not GEMINI_AVAILABLE:
        st.error("Gemini is not available. Install with: pip install google-generativeai")
        return None
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        
        # Get weather info
        weather = get_weather_info(user_location[0], user_location[1])
        
        prompt = f"""{GEMINI_ROUTING_PROMPT}

ROUTE REQUEST:
{json.dumps(route_request, indent=2)}

Starting Location: {user_location[0]}, {user_location[1]} ({LOCATION_NAME})

CURRENT WEATHER:
- Temperature: {weather['temperature']}
- Conditions: {weather['condition']}
- Wind: {weather['wind_speed']}

Generate a detailed route following the JSON format specified. Include weather considerations based on current conditions.
Consider that this is in {LOCATION_NAME}, a college town with the Hocking River, uptown area, and nearby parks.

Return ONLY valid JSON, no other text."""
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Extract JSON from response
        start_idx = text.find('{')
        end_idx = text.rfind('}') + 1
        
        if start_idx != -1 and end_idx > start_idx:
            json_str = text[start_idx:end_idx]
            route_data = json.loads(json_str)
            route_data['weather'] = weather
            return route_data
        else:
            st.error("Could not parse route data from Gemini")
            return None
            
    except Exception as e:
        st.error(f"Gemini API Error: {str(e)}")
        return None

def create_map(center, routes, route_details):
    """Create Folium map with routes and detailed markers"""
    m = folium.Map(location=center, zoom_start=14)
    
    colors = ['blue', 'red', 'green', 'purple', 'orange']
    
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
                popup=f"<b>Start</b><br>{details.get('start_name', 'Starting Point')}",
                icon=folium.Icon(color='green', icon='play')
            ).add_to(m)
            
            # End marker
            folium.Marker(
                route[-1], 
                popup=f"<b>End</b><br>{details.get('end_name', 'Destination')}",
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
    
    return m

# ------------------- SIDEBAR -------------------
with st.sidebar:
    st.title("⚙️ Configuration")
    
    # Ollama status
    ollama_status = has_ollama()
    st.write("**Ollama Status:**", "🟢 Connected" if ollama_status else "🔴 Not Connected")
    
    if not ollama_status:
        st.warning("Start Ollama with: `ollama serve`")
    
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
            st.success("✅ Gemini ready")
    
    st.divider()
    
    # Location
    st.subheader("📍 Your Location")
    st.write(f"**{LOCATION_NAME}**")
    st.write(f"Lat: {DEFAULT_LAT}, Lon: {DEFAULT_LON}")
    
    # Weather
    weather = get_weather_info(DEFAULT_LAT, DEFAULT_LON)
    st.write("**Current Weather:**")
    st.write(f"🌡️ {weather['temperature']}")
    st.write(f"☁️ {weather['condition']}")
    st.write(f"💨 {weather['wind_speed']}")
    
    st.divider()
    
    # Map controls
    st.subheader("🗺️ Map Controls")
    if st.button("Clear All Routes", use_container_width=True):
        st.session_state.routes = []
        st.session_state.route_details = []
        st.rerun()

# ------------------- MAIN UI -------------------
st.title("🏘️ Local Community Explorer")
st.markdown("*AI-powered route planning with local knowledge*")

# Create tabs
tab1, tab2 = st.tabs(["💬 AI Route Assistant", "🗺️ Map View"])

# ------------------- TAB 1: AI ASSISTANT -------------------
with tab1:
    st.subheader("Ask for Walking Routes & Local Exploration")
    
    # Example prompts
    with st.expander("💡 Example Requests"):
        st.markdown("""
        - "I want a walking route by the river"
        - "Find me a scenic bike path near downtown"
        - "Plan a 30-minute walk through parks"
        - "Show me a jogging route along the Hocking River"
        - "I need a wheelchair accessible route to uptown"
        """)
    
    # Display chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    # Chat input
    if prompt := st.chat_input("Ask for routes, recommendations, or local info..."):
        # Add user message
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.write(prompt)
        
        # Get AI response
        with st.chat_message("assistant"):
            if not ollama_status:
                error_msg = "⚠️ Ollama is not connected. Please start Ollama to use the assistant."
                st.error(error_msg)
                st.session_state.chat_history.append({"role": "assistant", "content": error_msg})
            else:
                with st.spinner("🤔 Understanding your request..."):
                    # Step 1: Ollama processes the request
                    ollama_response = ollama_query(prompt, system_prompt=OLLAMA_SYSTEM_PROMPT)
                    
                    # Check if this is a route request
                    route_request = extract_route_request(ollama_response)
                    
                    if route_request and GEMINI_AVAILABLE and st.session_state.gemini_api_key:
                        st.write("**Understanding your request...**")
                        st.info(ollama_response.replace('[ROUTE_REQUEST]', '').replace('[/ROUTE_REQUEST]', '').strip())
                        
                        # Step 2: Generate route with Gemini
                        with st.spinner("🗺️ Generating detailed route with Gemini..."):
                            route_data = gemini_generate_route(
                                route_request,
                                [DEFAULT_LAT, DEFAULT_LON],
                                st.session_state.gemini_api_key
                            )
                            
                            if route_data and 'waypoints' in route_data:
                                # Add route to map
                                st.session_state.routes.append(route_data['waypoints'])
                                st.session_state.route_details.append({
                                    'start_name': route_request.get('from', 'Start'),
                                    'end_name': route_request.get('to', 'Destination'),
                                    'points_of_interest': route_data.get('points_of_interest', [])
                                })
                                
                                # Display route details
                                st.success("✅ Route Generated!")
                                
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.metric("Distance", route_data.get('total_distance', 'N/A'))
                                    st.metric("Est. Time", route_data.get('estimated_time', 'N/A'))
                                with col2:
                                    st.metric("Temperature", route_data['weather']['temperature'])
                                    st.metric("Conditions", route_data['weather']['condition'])
                                
                                st.write("**📍 Route Description:**")
                                st.write(route_data.get('route_description', 'No description available'))
                                
                                st.write("**🌊 Surface Types:**", ", ".join(route_data.get('surface_types', [])))
                                st.write("**♿ Accessibility:**", route_data.get('accessibility', 'N/A'))
                                st.write("**🌤️ Weather Considerations:**", route_data.get('weather_considerations', 'N/A'))
                                st.write("**⏰ Best Times:**", route_data.get('best_times', 'N/A'))
                                
                                if route_data.get('points_of_interest'):
                                    st.write("**🎯 Points of Interest:**")
                                    for poi in route_data['points_of_interest']:
                                        st.write(f"  • {poi}")
                                
                                response_text = f"Route generated! Check the Map View tab to see your route. {len(route_data['waypoints'])} waypoints created."
                            else:
                                response_text = "Sorry, I couldn't generate a route. Please try rephrasing your request."
                        
                    elif route_request and not st.session_state.gemini_api_key:
                        response_text = ollama_response + "\n\n⚠️ Please enter your Gemini API key in the sidebar to generate routes."
                    elif route_request and not GEMINI_AVAILABLE:
                        response_text = ollama_response + "\n\n⚠️ Please install google-generativeai: pip install google-generativeai"
                    else:
                        # General conversation
                        response_text = ollama_response
                        st.write(response_text)
                    
                    st.session_state.chat_history.append({"role": "assistant", "content": response_text})

# ------------------- TAB 2: MAP VIEW -------------------
with tab2:
    st.subheader("Interactive Route Map")
    
    if st.session_state.routes:
        # Show route summary
        st.write(f"**Active Routes:** {len(st.session_state.routes)}")
        
        for idx in range(len(st.session_state.routes)):
            with st.expander(f"Route {idx + 1} Details"):
                details = st.session_state.route_details[idx] if idx < len(st.session_state.route_details) else {}
                st.write(f"**From:** {details.get('start_name', 'Start')}")
                st.write(f"**To:** {details.get('end_name', 'End')}")
                st.write(f"**Waypoints:** {len(st.session_state.routes[idx])}")
                
                if st.button(f"🗑️ Remove Route {idx + 1}", key=f"remove_{idx}"):
                    st.session_state.routes.pop(idx)
                    if idx < len(st.session_state.route_details):
                        st.session_state.route_details.pop(idx)
                    st.rerun()
    else:
        st.info("No routes yet. Ask the AI assistant to create a walking route!")
    
    # Create and display map
    m = create_map(st.session_state.map_center, st.session_state.routes, st.session_state.route_details)
    st_folium(m, width=None, height=600, key="main_map")

# ------------------- FOOTER -------------------
st.divider()
st.caption(f"📍 {LOCATION_NAME} | Routes: {len(st.session_state.routes)} | Messages: {len(st.session_state.chat_history)}")