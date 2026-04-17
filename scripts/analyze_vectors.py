import json
import math
from pathlib import Path

PROJ_ROOT = Path(__file__).resolve().parent.parent

with open(PROJ_ROOT / 'path_analysis_倉位含編號.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("Truth Data Navigation (first 20):")
for i in range(1, min(20, len(data))):
    p1 = data[i-1]
    p2 = data[i]
    dx = p2['cx'] - p1['cx']
    dy = p2['cy'] - p1['cy']
    dist = math.hypot(dx, dy)
    print(f"{p1['raw']:>5} -> {p2['raw']:>5}: dx={dx:8.1f}, dy={dy:8.1f}, dist={dist:8.1f}")
    
print("-" * 50)
print("Truth Data Navigation (mid 20):")
mid = len(data) // 2
for i in range(mid, min(mid+20, len(data))):
    p1 = data[i-1]
    p2 = data[i]
    dx = p2['cx'] - p1['cx']
    dy = p2['cy'] - p1['cy']
    dist = math.hypot(dx, dy)
    print(f"{p1['raw']:>5} -> {p2['raw']:>5}: dx={dx:8.1f}, dy={dy:8.1f}, dist={dist:8.1f}")
