import json
from main_pipeline import _categorize_texts
from cad_processor import assign_sequence_by_route

def test_regex_bug():
    print("--- Test Regex Bug ---")
    texts = [
        {"text": "120", "color": 7},       # Box ID smaller than 500
        {"text": "2000", "color": 2},    # Dimension (Color 2)
        {"text": "2000", "color": 6},    # Dimension (Color 6)
        {"text": "2300", "color": 7}     # It's a pure number > 500, even if wrong color, it's a Dims.
    ]
    
    boxes, dims, attrs = _categorize_texts(texts)
    print("Boxes:", [b["text"] for b in boxes])
    print("Dims:", [d["text"] for d in dims])
    
    # We assert that color 7 texts go to boxes
    assert "120" in [b["text"] for b in boxes], "Box '120' was NOT placed in boxes!"
    assert "2300" in [d["text"] for d in dims], "Box '2300' was NOT placed in dims!"
    assert "2000" in [d["text"] for d in dims], "Dimension '2000' was NOT placed in dims!"

def test_sorting_bug():
    print("--- Test Sorting Bug ---")
    # two perfectly opposing boxes. Same distance along route!
    spaces = [
        {"min_x": 0, "max_x": 100, "min_y": 500, "max_y": 600}, # Top box
        {"min_x": 0, "max_x": 100, "min_y": 0, "max_y": 100}   # Bottom box
    ]
    # Route polyline goes exactly through the middle horizontal (from x=-1000 to x=1000, y=300)
    route_polyline = [[-1000, 300], [1000, 300]]
    
    # First trial
    sorted_spaces_1 = assign_sequence_by_route(spaces, route_polyline, 1, [])
    order_1 = [s["unit_id"] for s in sorted_spaces_1]
    
    # Reverse input list and run second trial to simulate unstable sets
    sorted_spaces_2 = assign_sequence_by_route(spaces[::-1], route_polyline, 1, [])
    order_2 = [s["unit_id"] for s in sorted_spaces_2]
    
    print("Order Trial 1:", order_1)
    print("Order Trial 2:", order_2)
    
    # If the system is deterministic, the output order should NOT depend on the input list order
    assert sorted_spaces_1[0]["min_y"] == sorted_spaces_2[0]["min_y"], "Sorting is non-deterministic (unstable)!"

if __name__ == "__main__":
    try:
        test_regex_bug()
    except AssertionError as e:
        print("[FAIL] Regex Bug Failed:", e)
        
    try:
        test_sorting_bug()
    except AssertionError as e:
        print("[FAIL] Sorting Bug Failed:", e)
