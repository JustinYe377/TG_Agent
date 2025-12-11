# evaluator.py
import math
import re
from datetime import datetime
from pathlib import Path
import json

class RouteEvaluator:
    """
    Comprehensive route quality evaluator.
    Checks: event proximity, route efficiency, speed sanity, 
    geofence, completeness, waypoint quality.
    """
    
    def __init__(self, target_lat=39.3292, target_lon=-82.1013, radius_miles=5.0):
        self.center = (target_lat, target_lon)
        self.radius = radius_miles
        
        # Bounding box for Athens, OH
        self.bounds = {
            'min_lat': 39.2, 'max_lat': 39.45,
            'min_lon': -82.25, 'max_lon': -81.95
        }
        
        # Scoring weights (total = 100)
        self.weights = {
            'event_proximity': 25,
            'route_efficiency': 20,
            'speed_sanity': 20,
            'geofence': 15,
            'completeness': 10,
            'waypoint_quality': 10
        }
        
        # Walking speed bounds (mph)
        self.min_walk_speed = 1.5
        self.max_walk_speed = 4.5

    def haversine_distance(self, coord1, coord2):
        """Calculate distance in miles between two lat/lon points"""
        R = 3958.8  # Earth radius in miles
        lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
        lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    def extract_number(self, text):
        """Extract first number from string"""
        try:
            match = re.search(r"(\d+(\.\d+)?)", str(text))
            return float(match.group(1)) if match else 0.0
        except:
            return 0.0

    def load_events(self):
        """Load events from events.json"""
        try:
            events_file = Path("events.json")
            if events_file.exists():
                with open(events_file, 'r') as f:
                    data = json.load(f)
                    return data.get("events", [])
            return []
        except:
            return []

    def score_route(self, route_data):
        """
        Main scoring function. Returns total score and detailed report.
        """
        report = {
            'total_score': 0,
            'max_score': 100,
            'checks': {},
            'warnings': [],
            'summary': ''
        }
        
        waypoints = route_data.get('waypoints', [])
        
        # Critical failure: no waypoints
        if not waypoints or len(waypoints) < 2:
            report['total_score'] = 0
            report['warnings'].append("CRITICAL: No valid waypoints found")
            report['summary'] = "Route failed - no waypoints"
            return report['total_score'], report
        
        # Run all checks
        report['checks']['completeness'] = self._check_completeness(route_data)
        report['checks']['waypoint_quality'] = self._check_waypoint_quality(waypoints)
        report['checks']['geofence'] = self._check_geofence(waypoints)
        report['checks']['route_efficiency'] = self._check_efficiency(waypoints)
        report['checks']['speed_sanity'] = self._check_speed(route_data, waypoints)
        report['checks']['event_proximity'] = self._check_event_proximity(route_data, waypoints)
        
        # Calculate total score
        total = 0
        for check_name, check_result in report['checks'].items():
            total += check_result['score']
            if check_result.get('warnings'):
                report['warnings'].extend(check_result['warnings'])
        
        report['total_score'] = int(total)
        
        # Generate summary
        if total >= 80:
            report['summary'] = "Good quality route"
        elif total >= 60:
            report['summary'] = "Acceptable route with some issues"
        elif total >= 40:
            report['summary'] = "Poor quality route - review warnings"
        else:
            report['summary'] = "Low quality route - significant issues"
        
        return report['total_score'], report

    def _check_completeness(self, route_data):
        """Check if route has all required fields"""
        result = {
            'name': 'Completeness',
            'score': 0,
            'max': self.weights['completeness'],
            'details': [],
            'warnings': []
        }
        
        required_fields = ['waypoints', 'total_distance', 'estimated_time']
        optional_fields = ['route_description', 'points_of_interest', 'local_events']
        
        # Required fields (60% of score)
        required_present = 0
        for field in required_fields:
            if route_data.get(field):
                required_present += 1
                result['details'].append(f"{field}: present")
            else:
                result['warnings'].append(f"Missing required field: {field}")
        
        required_score = (required_present / len(required_fields)) * 0.6 * result['max']
        
        # Optional fields (40% of score)
        optional_present = 0
        for field in optional_fields:
            if route_data.get(field):
                optional_present += 1
        
        optional_score = (optional_present / len(optional_fields)) * 0.4 * result['max']
        
        result['score'] = round(required_score + optional_score, 1)
        result['details'].append(f"Required: {required_present}/{len(required_fields)}, Optional: {optional_present}/{len(optional_fields)}")
        
        return result

    def _check_waypoint_quality(self, waypoints):
        """Check waypoint count, duplicates, and spacing"""
        result = {
            'name': 'Waypoint Quality',
            'score': 0,
            'max': self.weights['waypoint_quality'],
            'details': [],
            'warnings': []
        }
        
        count = len(waypoints)
        
        # Check count (want at least 5 for a smooth route)
        if count >= 10:
            count_score = 1.0
        elif count >= 5:
            count_score = 0.8
        elif count >= 3:
            count_score = 0.5
        else:
            count_score = 0.2
            result['warnings'].append(f"Too few waypoints ({count}) for smooth route")
        
        result['details'].append(f"Waypoint count: {count}")
        
        # Check for duplicates
        unique_points = set()
        duplicates = 0
        for wp in waypoints:
            key = (round(wp[0], 5), round(wp[1], 5))
            if key in unique_points:
                duplicates += 1
            unique_points.add(key)
        
        if duplicates > 0:
            duplicate_penalty = min(duplicates * 0.1, 0.3)
            count_score -= duplicate_penalty
            result['warnings'].append(f"Found {duplicates} duplicate waypoints")
        
        result['details'].append(f"Unique points: {len(unique_points)}")
        
        # Check spacing (detect if points are too close together)
        tiny_gaps = 0
        for i in range(len(waypoints) - 1):
            dist = self.haversine_distance(waypoints[i], waypoints[i+1])
            if dist < 0.001:  # Less than 5 feet
                tiny_gaps += 1
        
        if tiny_gaps > count * 0.3:
            count_score -= 0.2
            result['warnings'].append(f"Many waypoints too close together ({tiny_gaps})")
        
        result['score'] = round(max(0, count_score) * result['max'], 1)
        
        return result

    def _check_geofence(self, waypoints):
        """Check if waypoints are within Athens area"""
        result = {
            'name': 'Geofence',
            'score': 0,
            'max': self.weights['geofence'],
            'details': [],
            'warnings': []
        }
        
        in_bounds = 0
        out_of_bounds = []
        
        for i, wp in enumerate(waypoints):
            lat, lon = wp[0], wp[1]
            if (self.bounds['min_lat'] <= lat <= self.bounds['max_lat'] and 
                self.bounds['min_lon'] <= lon <= self.bounds['max_lon']):
                in_bounds += 1
            else:
                out_of_bounds.append(i)
        
        total = len(waypoints)
        ratio = in_bounds / total if total > 0 else 0
        
        result['score'] = round(ratio * result['max'], 1)
        result['details'].append(f"In bounds: {in_bounds}/{total} waypoints")
        
        if out_of_bounds:
            result['warnings'].append(f"Waypoints outside Athens area: indices {out_of_bounds[:5]}{'...' if len(out_of_bounds) > 5 else ''}")
        
        return result

    def _check_efficiency(self, waypoints):
        """Check if route is reasonably direct (not zigzagging)"""
        result = {
            'name': 'Route Efficiency',
            'score': 0,
            'max': self.weights['route_efficiency'],
            'details': [],
            'warnings': []
        }
        
        if len(waypoints) < 2:
            result['score'] = 0
            return result
        
        # Calculate actual path distance
        path_distance = 0
        for i in range(len(waypoints) - 1):
            path_distance += self.haversine_distance(waypoints[i], waypoints[i+1])
        
        # Calculate direct distance (start to end)
        direct_distance = self.haversine_distance(waypoints[0], waypoints[-1])
        
        # Efficiency ratio (1.0 = perfectly direct, lower = more wandering)
        # For walking routes, 0.3-0.7 is reasonable (you want some exploration)
        if direct_distance > 0:
            ratio = direct_distance / path_distance if path_distance > 0 else 0
        else:
            # Circular route (start = end)
            ratio = 0.5  # Give neutral score for loops
            result['details'].append("Circular route detected")
        
        result['details'].append(f"Path distance: {path_distance:.2f} mi")
        result['details'].append(f"Direct distance: {direct_distance:.2f} mi")
        result['details'].append(f"Efficiency ratio: {ratio:.2f}")
        
        # Score based on ratio
        # 0.25-0.85 is ideal for exploratory walks
        if 0.25 <= ratio <= 0.85:
            score_ratio = 1.0
        elif ratio > 0.85:
            # Too direct (might miss sights)
            score_ratio = 0.8
            result['details'].append("Route is very direct")
        elif ratio < 0.25:
            # Too wandering
            score_ratio = ratio / 0.25 * 0.6
            result['warnings'].append("Route appears to zigzag excessively")
        else:
            score_ratio = 0.5
        
        result['score'] = round(score_ratio * result['max'], 1)
        
        return result

    def _check_speed(self, route_data, waypoints):
        """Check if time/distance implies reasonable walking speed"""
        result = {
            'name': 'Speed Sanity',
            'score': 0,
            'max': self.weights['speed_sanity'],
            'details': [],
            'warnings': []
        }
        
        # Get claimed values
        claimed_distance = self.extract_number(route_data.get('total_distance', '0'))
        claimed_time = self.extract_number(route_data.get('estimated_time', '0'))
        
        # Calculate actual distance from waypoints
        actual_distance = 0
        for i in range(len(waypoints) - 1):
            actual_distance += self.haversine_distance(waypoints[i], waypoints[i+1])
        
        result['details'].append(f"Claimed distance: {claimed_distance} mi")
        result['details'].append(f"Calculated distance: {actual_distance:.2f} mi")
        result['details'].append(f"Claimed time: {claimed_time} min")
        
        score = 0.0
        
        # Check distance accuracy (50% of this check's score)
        if claimed_distance > 0:
            distance_error = abs(actual_distance - claimed_distance) / claimed_distance
            if distance_error <= 0.2:
                score += 0.5
                result['details'].append(f"Distance error: {distance_error:.1%} (acceptable)")
            elif distance_error <= 0.5:
                score += 0.3
                result['details'].append(f"Distance error: {distance_error:.1%} (high)")
            else:
                result['warnings'].append(f"Distance mismatch: claimed {claimed_distance} mi vs calculated {actual_distance:.2f} mi")
        
        # Check speed sanity (50% of this check's score)
        if claimed_time > 0 and claimed_distance > 0:
            speed_mph = claimed_distance / (claimed_time / 60)
            result['details'].append(f"Implied speed: {speed_mph:.1f} mph")
            
            if self.min_walk_speed <= speed_mph <= self.max_walk_speed:
                score += 0.5
                result['details'].append("Speed is reasonable for walking")
            elif speed_mph < self.min_walk_speed:
                score += 0.3
                result['details'].append("Speed is slow (may include stops)")
            elif speed_mph <= 6.0:
                score += 0.3
                result['warnings'].append(f"Speed ({speed_mph:.1f} mph) is fast - jogging pace")
            else:
                result['warnings'].append(f"Speed ({speed_mph:.1f} mph) is unrealistic for walking")
        
        result['score'] = round(score * result['max'], 1)
        
        return result

    def _check_event_proximity(self, route_data, waypoints):
        """Check if route passes near claimed events"""
        result = {
            'name': 'Event Proximity',
            'score': 0,
            'max': self.weights['event_proximity'],
            'details': [],
            'warnings': []
        }
        
        # Load actual events with coordinates
        events = self.load_events()
        geocoded_events = [e for e in events if e.get('geocoded') and e.get('lat') and e.get('lon')]
        
        if not geocoded_events:
            result['score'] = result['max'] * 0.5  # Neutral if no events to check
            result['details'].append("No geocoded events to verify against")
            return result
        
        # Get events mentioned in route
        route_events = route_data.get('local_events', [])
        route_poi = route_data.get('points_of_interest', [])
        
        if not route_events and not route_poi:
            result['score'] = result['max'] * 0.5  # Neutral if route claims no events
            result['details'].append("Route does not reference specific events")
            return result
        
        # Check proximity of route to each geocoded event
        events_near_route = 0
        proximity_threshold = 0.2  # miles
        
        for event in geocoded_events:
            event_coord = (event['lat'], event['lon'])
            min_distance = float('inf')
            
            # Find minimum distance from any waypoint to this event
            for wp in waypoints:
                dist = self.haversine_distance(wp, event_coord)
                min_distance = min(min_distance, dist)
            
            if min_distance <= proximity_threshold:
                events_near_route += 1
                result['details'].append(f"PASS: {event['name']} - {min_distance:.2f} mi from route")
            else:
                result['details'].append(f"MISS: {event['name']} - {min_distance:.2f} mi from route")
        
        # Score based on how many events the route passes
        if geocoded_events:
            ratio = events_near_route / len(geocoded_events)
            result['score'] = round(ratio * result['max'], 1)
            result['details'].append(f"Route passes {events_near_route}/{len(geocoded_events)} events within {proximity_threshold} mi")
            
            if events_near_route == 0:
                result['warnings'].append("Route does not pass near any known events")
        
        return result

    def format_report(self, report):
        """Format report as readable string"""
        lines = []
        lines.append(f"{'='*50}")
        lines.append(f"ROUTE QUALITY REPORT: {report['total_score']}/{report['max_score']}")
        lines.append(f"{'='*50}")
        lines.append(f"Summary: {report['summary']}")
        lines.append("")
        
        for check_name, check in report['checks'].items():
            status = "PASS" if check['score'] >= check['max'] * 0.7 else "WARN" if check['score'] >= check['max'] * 0.4 else "FAIL"
            lines.append(f"[{status}] {check['name']}: {check['score']}/{check['max']}")
            for detail in check['details']:
                lines.append(f"      {detail}")
        
        if report['warnings']:
            lines.append("")
            lines.append("WARNINGS:")
            for warning in report['warnings']:
                lines.append(f"  - {warning}")
        
        return "\n".join(lines)