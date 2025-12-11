# evaluator.py
import math
import re

class RouteEvaluator:
    def __init__(self, target_lat=39.3292, target_lon=-82.1013, radius_miles=5.0):
        self.center = (target_lat, target_lon)
        self.radius = radius_miles
        # Bounding box for Athens, OH
        self.bounds = {
            'min_lat': 39.2, 'max_lat': 39.45,
            'min_lon': -82.25, 'max_lon': -81.95
        }

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

    def extract_miles(self, distance_str):
        try:
            match = re.search(r"(\d+(\.\d+)?)", str(distance_str))
            return float(match.group(1)) if match else 0.0
        except:
            return 0.0

    def score_route(self, route_data):
        score = 100
        logs = []
        
        waypoints = route_data.get('waypoints', [])
        if not waypoints or len(waypoints) < 2:
            return 0, ["❌ Critical: No valid waypoints found"]

        # 1. Structural Check
        required = ['total_distance', 'local_events', 'estimated_time']
        missing = [k for k in required if k not in route_data]
        if missing:
            score -= (10 * len(missing))
            logs.append(f"⚠️ Missing keys: {missing}")

        # 2. Geofence Check
        out_of_bounds = 0
        for wp in waypoints:
            lat, lon = wp[0], wp[1]
            if not (self.bounds['min_lat'] <= lat <= self.bounds['max_lat'] and 
                    self.bounds['min_lon'] <= lon <= self.bounds['max_lon']):
                out_of_bounds += 1
        
        if out_of_bounds > 0:
            score -= int((out_of_bounds / len(waypoints)) * 40)
            logs.append(f"⚠️ {out_of_bounds} waypoints outside Athens area")

        # 3. Physics Check (Distance)
        calc_dist = sum(self.haversine_distance(waypoints[i], waypoints[i+1]) for i in range(len(waypoints)-1))
        claimed_dist = self.extract_miles(route_data.get('total_distance', '0'))
        
        if claimed_dist > 0:
            variance = abs(calc_dist - claimed_dist) / claimed_dist
            if variance > 0.25: # 25% tolerance
                score -= 30
                logs.append(f"⚠️ Hallucination: Calc {calc_dist:.2f}m != Claimed {claimed_dist}m")
            else:
                logs.append(f"✅ Physics verified (Variance: {variance:.1%})")
        
        return max(0, int(score)), logs