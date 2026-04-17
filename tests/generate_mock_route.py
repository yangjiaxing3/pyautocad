import json
import os

def generate_mock():
    entities = []
    
    # helper to add lines for a storage box
    def add_rect(x1, y1, x2, y2, color=3): 
        entities.append({"type": "AcDbLine", "start": [x1, y1], "end": [x2, y1], "color": color})
        entities.append({"type": "AcDbLine", "start": [x2, y1], "end": [x2, y2], "color": color})
        entities.append({"type": "AcDbLine", "start": [x2, y2], "end": [x1, y2], "color": color})
        entities.append({"type": "AcDbLine", "start": [x1, y2], "end": [x1, y1], "color": color})
        
        # Dimensions
        entities.append({"type": "AcDbText", "text": str(abs(x2-x1)), "x": (x1+x2)/2, "y": y1-100, "color": 2})
        entities.append({"type": "AcDbText", "text": str(abs(y2-y1)), "x": x1-100, "y": (y1+y2)/2, "color": 6})
        
    # Generate 3 spaces with different colors (Color 3=單2300, Color 5=雙3200, Color 8=單2000)
    add_rect(0, 0, 2000, 2000, 3)     # Near (1000, 1000) -> Dist from start = 2000
    add_rect(0, 3000, 2000, 5000, 5)  # Near (1000, 4000) -> Dist from start = 5000
    add_rect(3000, 3000, 5000, 5000, 8) # Near (4000, 4000)-> Dist from start = 8000
    
    # POLYLINE ROUTE. Starts far left (-1000, 1000). Passes directly through all 3 centers.
    entities.append({
        "type": "AcDbPolyline",
        "layer": "ROUTE_FLOW",
        "vertices": [
            [-1000, 1000],
            [1000, 1000],
            [1000, 4000],
            [5000, 4000]
        ]
    })
    
    # Notice: NO TEXT containing unit identifiers like "1", "2" or "HD00" exists in this payload!
    
    os.makedirs('tests', exist_ok=True)
    with open('cad_dump.json', 'w', encoding='utf-8') as f:
        json.dump(entities, f, ensure_ascii=False, indent=2)
        
    print("Generated cad_dump.json containing solely geometry and a Route Polyline!")

if __name__ == "__main__":
    generate_mock()
