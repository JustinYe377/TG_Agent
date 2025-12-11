# main.py
import streamlit as st
import folium
from streamlit_folium import st_folium

# Import our modules
import config
import utils
import agent_logic
from evaluator import RouteEvaluator

# --- Page Config ---
st.set_page_config(page_title="Local Community Explorer", layout="wide")

# --- Session State ---
if "routes" not in st.session_state: st.session_state.routes = []
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "gemini_api_key" not in st.session_state: st.session_state.gemini_api_key = ""
if "ors_api_key" not in st.session_state: st.session_state.ors_api_key = ""
if "map_center" not in st.session_state: st.session_state.map_center = [config.DEFAULT_LAT, config.DEFAULT_LON]
if "debug_mode" not in st.session_state: st.session_state.debug_mode = False
if "last_evaluation" not in st.session_state: st.session_state.last_evaluation = None
if "last_route_data" not in st.session_state: st.session_state.last_route_data = None

# Initialize usage tracking
utils.init_gemini_usage()

# --- Sidebar ---
with st.sidebar:
    st.title("Config")
    
    # --- Status Indicators ---
    ollama_ok = agent_logic.check_ollama()
    st.write("Ollama:", "Ready" if ollama_ok else "Offline")
    
    # --- API Keys ---
    key = st.text_input("Gemini API Key", value=st.session_state.gemini_api_key, type="password")
    if key: st.session_state.gemini_api_key = key
    
    ors_key = st.text_input("OpenRouteService Key", value=st.session_state.ors_api_key, type="password", 
                            help="Free at openrouteservice.org - enables real walking routes")
    if ors_key: st.session_state.ors_api_key = ors_key
    
    if not st.session_state.ors_api_key:
        st.caption("Without ORS key, routes will be straight lines")
    
    st.divider()
    
    # --- Event Management ---
    st.subheader("Local Events")
    
    last_updated = agent_logic.get_events_last_updated()
    st.caption(f"Last updated: {last_updated}")
    
    # Load current events count
    events_data = agent_logic.load_events_from_file()
    events_count = len(events_data.get("events", [])) if events_data else 0
    st.write(f"Events loaded: {events_count}")
    
    # Refresh button
    if st.button("Refresh Events", disabled=not st.session_state.gemini_api_key):
        with st.spinner("Fetching real events from web..."):
            result = agent_logic.fetch_real_events(
                config.LOCATION_NAME,
                st.session_state.gemini_api_key,
                num_events=5
            )
            
            if result.get("success"):
                agent_logic.save_events_to_file(result)
                st.success(f"Found {len(result['events'])} events!")
                st.rerun()
            else:
                st.error(result.get("error", "Unknown error"))
    
    if not st.session_state.gemini_api_key:
        st.caption("Enter API key to refresh events")
    
    st.divider()
    
    # --- Gemini Usage Stats ---
    st.subheader("Gemini Usage")
    
    stats = utils.get_usage_stats()
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            "Requests", 
            f"{stats['requests_today']}", 
            delta=f"/ {stats['requests_limit']}"
        )
    with col2:
        st.metric(
            "Tokens", 
            f"{stats['tokens_today']:,}", 
            delta=f"/ 1M"
        )
    
    # Progress bars
    requests_pct = stats['requests_today'] / stats['requests_limit']
    tokens_pct = stats['tokens_today'] / stats['tokens_limit']
    
    st.progress(min(requests_pct, 1.0), text=f"Requests: {requests_pct:.1%}")
    st.progress(min(tokens_pct, 1.0), text=f"Tokens: {tokens_pct:.1%}")
    
    # Warning
    if stats['is_warning']:
        st.warning("Approaching daily request limit!")
    
    st.caption(f"Last request: {stats['last_request_tokens']} tokens")
    
    st.divider()
    
    # --- Debug Mode Toggle ---
    st.session_state.debug_mode = st.toggle("Debug Mode", value=st.session_state.debug_mode)
    
    # --- Self-Test ---
    if st.button("Run Self-Test"):
        st.info("Running diagnostic on 'River Walk'...")
        evaluator = RouteEvaluator()
        st.write("Diagnostic complete (See Evaluator.py for details)")

# --- Main UI ---
st.title(f"{config.LOCATION_NAME} Explorer")

# Show events status banner
events_data = agent_logic.load_events_from_file()
if not events_data or not events_data.get("events"):
    st.warning("No events loaded. Click 'Refresh Events' in the sidebar to fetch real local events.")

tab1, tab2, tab3, tab4 = st.tabs(["Assistant", "Map", "Events", "Evaluator"])

with tab1:
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            
    if prompt := st.chat_input("Where should I go?"):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.write(prompt)
        
        with st.chat_message("assistant"):
            if not ollama_ok:
                st.error("Please start Ollama!")
            else:
                # 1. Ollama Intent (with real events)
                with st.spinner("Thinking..."):
                    resp = agent_logic.query_ollama_with_events(prompt)
                    route_req = utils.extract_route_request(resp)
                    
                    # Display response (without the tags)
                    clean_resp = resp.replace('[ROUTE_REQUEST]', '').split('[/ROUTE_REQUEST]')[0]
                    st.write(clean_resp)
                    
                    # Debug: Show extraction status (only if debug mode)
                    if st.session_state.debug_mode:
                        with st.expander("Debug: Route Extraction"):
                            if route_req:
                                st.success(f"Route request found: {route_req}")
                            else:
                                st.warning("No [ROUTE_REQUEST] tags found in response")
                                st.text("Raw response (last 500 chars):")
                                st.code(resp[-500:] if len(resp) > 500 else resp)
                    
                    # 2. Gemini Route Generation
                    if route_req and st.session_state.gemini_api_key:
                        with st.spinner("Planning route..."):
                            route_data = agent_logic.generate_gemini_route(
                                route_req, 
                                [config.DEFAULT_LAT, config.DEFAULT_LON], 
                                st.session_state.gemini_api_key,
                                st.session_state.ors_api_key
                            )
                            
                            if route_data:
                                # Debug: Show route data (only if debug mode)
                                if st.session_state.debug_mode:
                                    with st.expander("Debug: Gemini Route Data"):
                                        st.write(f"Route type: {route_data.get('route_type', 'unknown')}")
                                        st.write(f"Waypoints count: {len(route_data.get('waypoints', []))}")
                                        if route_data.get('real_distance'):
                                            st.write(f"Real distance: {route_data['real_distance']}")
                                            st.write(f"Real duration: {route_data['real_duration']}")
                                        st.write(f"First 3 waypoints: {route_data.get('waypoints', [])[:3]}")
                                
                                # 3. Self-Testing/Scoring
                                evaluator = RouteEvaluator()
                                score, report = evaluator.score_route(route_data)
                                
                                # Store evaluation for Evaluator tab
                                st.session_state.last_evaluation = report
                                st.session_state.last_route_data = route_data
                                
                                # Display simple score with link to Evaluator tab
                                if score >= 80:
                                    st.success(f"Route Quality: {score}/100 - {report['summary']}")
                                elif score >= 60:
                                    st.info(f"Route Quality: {score}/100 - {report['summary']}")
                                elif score >= 40:
                                    st.warning(f"Route Quality: {score}/100 - {report['summary']}")
                                else:
                                    st.error(f"Route Quality: {score}/100 - {report['summary']}")
                                
                                st.caption("See Evaluator tab for detailed report")
                                    
                                # Save route
                                st.session_state.routes.append(route_data['waypoints'])
                                st.session_state.map_center = route_data['waypoints'][0]
                                st.success("Route added to map!")
                    
                    # Save assistant response
                    st.session_state.chat_history.append({"role": "assistant", "content": resp})

with tab2:
    m = folium.Map(location=st.session_state.map_center, zoom_start=14)
    
    # Add event markers
    events_data = agent_logic.load_events_from_file()
    if events_data and events_data.get("events"):
        for evt in events_data["events"]:
            if evt.get("geocoded") and evt.get("lat") and evt.get("lon"):
                folium.Marker(
                    [evt["lat"], evt["lon"]],
                    popup=f"{evt.get('name', 'Event')}<br>{evt.get('date', '')} {evt.get('time', '')}",
                    tooltip=evt.get('name', 'Event'),
                    icon=folium.Icon(color='purple', icon='star')
                ).add_to(m)
    
    # Add routes
    for route in st.session_state.routes:
        if len(route) > 0:
            folium.PolyLine(route, weight=5, color='blue').add_to(m)
            folium.Marker(route[0], icon=folium.Icon(color='green', icon='play')).add_to(m)
            folium.Marker(route[-1], icon=folium.Icon(color='red', icon='stop')).add_to(m)
            
    st_folium(m, height=600, width=None)

with tab3:
    st.subheader("Loaded Events")
    
    events_data = agent_logic.load_events_from_file()
    
    if events_data and events_data.get("events"):
        st.caption(f"Last updated: {agent_logic.get_events_last_updated()}")
        st.caption(f"Location: {events_data.get('location', 'Unknown')}")
        
        for i, event in enumerate(events_data["events"], 1):
            with st.expander(f"{i}. {event.get('name', 'Unnamed Event')}", expanded=(i == 1)):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Location:** {event.get('location', 'TBD')}")
                    st.write(f"**Date:** {event.get('date', 'TBD')}")
                    st.write(f"**Time:** {event.get('time', 'TBD')}")
                with col2:
                    st.write(f"**Category:** {event.get('category', 'other')}")
                    st.write(f"**Cost:** {event.get('cost', 'Unknown')}")
                    # Show geocoding status
                    if event.get('geocoded'):
                        st.write(f"**Coords:** {event.get('lat', 0):.4f}, {event.get('lon', 0):.4f}")
                    else:
                        st.write(f"**Coords:** Not found")
                
                st.write(f"**Details:** {event.get('description', 'No description available')}")
                
                if event.get('source_url'):
                    st.markdown(f"[Source]({event['source_url']})")
    else:
        st.info("No events loaded yet. Click 'Refresh Events' in the sidebar to fetch real local events.")

with tab4:
    st.subheader("Route Quality Evaluator")
    
    if st.session_state.last_evaluation:
        report = st.session_state.last_evaluation
        route_data = st.session_state.last_route_data
        
        # Overall score
        score = report['total_score']
        st.metric("Overall Score", f"{score}/100", delta=report['summary'])
        
        st.divider()
        
        # Route info
        if route_data:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Waypoints", len(route_data.get('waypoints', [])))
            with col2:
                st.metric("Distance", route_data.get('real_distance', route_data.get('total_distance', 'N/A')))
            with col3:
                st.metric("Duration", route_data.get('real_duration', route_data.get('estimated_time', 'N/A')))
        
        st.divider()
        
        # Individual checks
        st.subheader("Check Results")
        
        for check_name, check in report['checks'].items():
            pct = check['score'] / check['max'] if check['max'] > 0 else 0
            
            # Status indicator
            if pct >= 0.7:
                status = "PASS"
                color = "green"
            elif pct >= 0.4:
                status = "WARN"
                color = "orange"
            else:
                status = "FAIL"
                color = "red"
            
            # Display check
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{check['name']}**")
            with col2:
                st.write(f"[{status}] {check['score']}/{check['max']}")
            
            # Progress bar
            st.progress(pct)
            
            # Details
            with st.expander(f"Details for {check['name']}"):
                for detail in check['details']:
                    st.text(detail)
                if check.get('warnings'):
                    st.text("")
                    st.text("Warnings:")
                    for warning in check['warnings']:
                        st.warning(warning)
            
            st.text("")  # Spacing
        
        # All warnings
        if report['warnings']:
            st.divider()
            st.subheader("All Warnings")
            for warning in report['warnings']:
                st.warning(warning)
    
    else:
        st.info("No route evaluated yet. Request a route in the Assistant tab to see evaluation results here.")