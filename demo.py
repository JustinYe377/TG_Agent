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
OLLAMA_SYSTEM_PROMPT = f"""You are an enthusiastic community connector for {LOCATION_NAME}. Your mission is to get people OUTSIDE and engaging with their community.

YOUR PERSONALITY:
- Proactive and encouraging (not passive)
- Assume people want to explore (don't ask too many clarifying questions)
- Push people to discover local events and connect with others
- Make confident suggestions based on context

YOUR APPROACH:
1. When someone mentions ANY outdoor activity → IMMEDIATELY suggest a route AND tie it to local events/activities
2. Don't ask "what kind of route?" - ASSUME and suggest the best option
3. Always include: route + local events happening nearby + social opportunities
4. Be pushy about community engagement (in a friendly way)

EXAMPLES:
User: "I want to walk by the river"
You: "Perfect! Let me get you a scenic river walk AND here's what's happening today:
[ROUTE_REQUEST]
Type: walking
From: Current location
To: Hocking River Trail via uptown
Preferences: Scenic riverfront, connect to local activities
Description: 2-mile river walk passing the Farmers Market (Saturdays 9am-1pm), Community Art Fair at Riverfront Park, and ends near campus coffee shops where local musicians perform
Events: Check out the Farmers Market, swing by the Art Fair, grab coffee at local spot
Social: Great chance to meet locals at the market and art fair
[/ROUTE_REQUEST]"

User: "I'm bored"
You: "Time to get out there! {LOCATION_NAME} has tons happening right now. Let me plan you a route to the most active spots:
[ROUTE_REQUEST]
Type: walking
From: Current location
To: Downtown event circuit
Preferences: High activity areas, social spots
Description: Walk through uptown → campus green (often has events) → downtown art district
Events: Live music at Coffee Shop X (7pm), Open Mic at Y (8pm), Weekly trivia at Z pub
Social: All these spots are buzzing tonight - perfect for meeting people
[/ROUTE_REQUEST]"

ALWAYS INCLUDE IN ROUTE REQUESTS:
- Actual route plan (don't wait for confirmation)
- Current/upcoming local events along the route
- Social opportunities (markets, cafes, gathering spots)
- Time-sensitive info ("happening NOW", "starts in 30min")

NEVER:
- Ask "what time?" or "how far?" - suggest something reasonable
- Say "let me know if you want..." - TELL them what they should do
- Be passive - be the friend who gets people off the couch

Remember: You're helping combat isolation. Be the enthusiastic local friend who always knows what's happening and pushes people to join in!

Current context: {LOCATION_NAME} - college town, Hocking River, Ohio University campus, uptown district, active arts scene, farmers markets, hiking trails nearby."""

GEMINI_ROUTING_PROMPT = """You are an energetic local event connector and route planner.

YOUR MISSION: Create routes that connect people to ACTIVE community life, not just point A to B.

YOUR ROLE:
1. Generate routes that pass through currently active areas
2. Research and include REAL local events happening now or soon
3. Suggest social opportunities along the route
4. Push people toward community engagement

CRITICAL: Include actual up-to-date information:
- Current weather and how it affects activities
- Time-sensitive events (happening today, this week)
- Popular local gathering spots
- Seasonal activities
- Community events, markets, festivals, meetups

OUTPUT FORMAT (JSON):
{
  "waypoints": [[lat, lon], [lat, lon], ...],
  "route_description": "Detailed path with event callouts",
  "total_distance": "X.X miles",
  "estimated_time": "XX minutes",
  "points_of_interest": ["Active spot 1 with current activity", "Event location 2"],
  "local_events": [
    {
      "name": "Event name",
      "location": "Where along route",
      "time": "When it happens",
      "description": "Why they should check it out"
    }
  ],
  "social_opportunities": ["Coffee shop with regulars", "Park where people gather", "Market happening now"],
  "surface_types": ["paved", "trail"],
  "accessibility": "accessibility info",
  "weather_considerations": "Current weather and what's happening despite/because of it",
  "best_times": "When most activities happen",
  "why_go_now": "Compelling reason to go TODAY/THIS WEEK - be pushy!"
}

IMPORTANT:
- Make routes pass through ACTIVE areas (not shortcuts)
- Prioritize routes with current events happening
- Include specific times for events ("Farmers Market: 9am-1pm TODAY")
- Be enthusiastic about getting people outside
- Use real-world knowledge of typical college town events
- Consider day of week and time for suggesting activities
- ALWAYS include a "why_go_now" that pushes people to act immediately"""

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
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # Get weather info
        weather = get_weather_info(user_location[0], user_location[1])
        
        # Get current day and time for context
        now = datetime.now()
        day_of_week = now.strftime("%A")
        current_time = now.strftime("%I:%M %p")
        
        prompt = f"""{GEMINI_ROUTING_PROMPT}

ROUTE REQUEST:
{json.dumps(route_request, indent=2)}

CONTEXT:
- Location: {user_location[0]}, {user_location[1]} ({LOCATION_NAME})
- Current Day: {day_of_week}
- Current Time: {current_time}
- Weather: {weather['temperature']}, {weather['condition']}, Wind: {weather['wind_speed']}

LOCATION INFO: {LOCATION_NAME} is a college town with Ohio University, Hocking River, uptown district, active arts and music scene, weekly farmers markets, local coffee shops, breweries, parks, and hiking trails.

CRITICAL COORDINATE REQUIREMENTS:
- Athens, OH is located at approximately 39.3292°N, -82.1013°W
- All waypoints MUST be within this area: Latitude 39.0-40.0, Longitude -83.0 to -81.0
- Generate 5-10 realistic waypoints that form an actual path
- Example waypoint: [39.3292, -82.1013] (downtown Athens)
- Example waypoint: [39.3248, -82.1012] (Ohio University)
- Example waypoint: [39.3350, -82.0950] (along Hocking River)

YOUR TASK:
1. Create a route that passes through ACTIVE community spaces
2. Research/suggest real events that typically happen on {day_of_week}s in college towns like this
3. Include specific gathering spots (markets, cafes, parks with activities)
4. Give them a compelling reason to go NOW, not later
5. Be enthusiastic and pushy - your goal is to get them off the couch!

Generate the complete JSON response with real event suggestions based on typical {day_of_week} activities in {LOCATION_NAME}."""
        
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
    m = folium.Map(location=center, zoom_start=14, tiles='OpenStreetMap')
    
    colors = ['blue', 'red', 'green', 'purple', 'orange']
    
    if not routes:
        # Add a center marker if no routes
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
    with st.expander("💡 Try These (Agent will push you to go out!)"):
        st.markdown("""
        - "I'm bored"
        - "Want to walk by the river"
        - "Need some exercise"
        - "What's happening today?"
        - "Looking for something to do"
        
        **Note:** This agent is proactive - it won't ask many questions, it'll just get you outside! 🚀
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
                                # Validate and add route to map
                                waypoints = route_data['waypoints']
                                
                                # Debug: Show waypoints
                                st.write(f"**🔍 Debug: Generated {len(waypoints)} waypoints**")
                                st.json(waypoints[:3])  # Show first 3 waypoints
                                
                                # Ensure waypoints are valid [lat, lon] pairs
                                valid_waypoints = []
                                for wp in waypoints:
                                    if isinstance(wp, (list, tuple)) and len(wp) == 2:
                                        try:
                                            lat, lon = float(wp[0]), float(wp[1])
                                            # Basic validation (Athens, OH area)
                                            if 39.0 < lat < 40.0 and -83.0 < lon < -81.0:
                                                valid_waypoints.append([lat, lon])
                                        except (ValueError, TypeError):
                                            continue
                                
                                if len(valid_waypoints) < 2:
                                    st.error(f"⚠️ Only {len(valid_waypoints)} valid waypoints generated. Creating simple route...")
                                    # Fallback: create simple route
                                    valid_waypoints = [
                                        [DEFAULT_LAT, DEFAULT_LON],
                                        [DEFAULT_LAT + 0.01, DEFAULT_LON + 0.01]
                                    ]
                                
                                st.session_state.routes.append(valid_waypoints)
                                st.session_state.route_details.append({
                                    'start_name': route_request.get('from', 'Start'),
                                    'end_name': route_request.get('to', 'Destination'),
                                    'points_of_interest': route_data.get('points_of_interest', [])
                                })
                                
                                # Update map center to first waypoint
                                st.session_state.map_center = valid_waypoints[0]
                                
                                # Display route details
                                st.success("✅ Route Generated! Here's what's happening:")
                                
                                # Prominent "Why Go Now" section
                                if route_data.get('why_go_now'):
                                    st.warning(f"⚡ **{route_data['why_go_now']}**")
                                
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Distance", route_data.get('total_distance', 'N/A'))
                                with col2:
                                    st.metric("Est. Time", route_data.get('estimated_time', 'N/A'))
                                with col3:
                                    st.metric("Weather", f"{route_data['weather']['temperature']}, {route_data['weather']['condition']}")
                                
                                # Local Events - Most Important!
                                if route_data.get('local_events'):
                                    st.write("### 🎉 Local Events Along Your Route")
                                    for event in route_data['local_events']:
                                        with st.expander(f"📅 {event.get('name', 'Event')}", expanded=True):
                                            st.write(f"**📍 Location:** {event.get('location', 'TBD')}")
                                            st.write(f"**🕐 Time:** {event.get('time', 'TBD')}")
                                            st.write(f"**ℹ️ {event.get('description', '')}**")
                                
                                # Social Opportunities
                                if route_data.get('social_opportunities'):
                                    st.write("### 👥 Social Spots Along the Way")
                                    for spot in route_data['social_opportunities']:
                                        st.write(f"  • {spot}")
                                
                                # Route Description
                                with st.expander("📍 Detailed Route Description"):
                                    st.write(route_data.get('route_description', 'No description available'))
                                    st.write("**Surface Types:**", ", ".join(route_data.get('surface_types', [])))
                                    st.write("**Accessibility:**", route_data.get('accessibility', 'N/A'))
                                
                                # Points of Interest
                                if route_data.get('points_of_interest'):
                                    with st.expander("🎯 Points of Interest"):
                                        for poi in route_data['points_of_interest']:
                                            st.write(f"  • {poi}")
                                
                                response_text = f"🎉 Route ready! {len(valid_waypoints)} waypoints with {len(route_data.get('local_events', []))} events along the way. Check the Map View tab!"
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
    
    # Debug information
    with st.expander("🔧 Debug Info"):
        st.write(f"**Total Routes:** {len(st.session_state.routes)}")
        st.write(f"**Map Center:** {st.session_state.map_center}")
        if st.session_state.routes:
            st.write(f"**Last Route Waypoints:** {len(st.session_state.routes[-1])}")
            st.json(st.session_state.routes[-1])
    
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