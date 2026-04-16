import json
import re
import math

data = json.load(open('cad_dump.json', encoding='utf-8'))

texts = []
arrows = []

for d in data:
    if 'text' in d:
        t = d['text'].strip()
        if t:
            texts.append(d)
    if 'type' in d and 'Line' in d['type'] and d.get('color') in [6, 210, 211, 220, 255]: # pink colours?
        # A bit simplistic, but we will gather them
        arrows.append(d)

print(f"Filter: {len(texts)} texts, {len(arrows)} lines.")

# Let's categorize the texts so it's readable
boxes = []
dims = []
attrs = []

for t in texts:
    txt = t['text']
    # Check if number
    if re.match(r'^\d+(\.\d+)?$', txt):
        dims.append(t)
    elif '單' in txt or '雙' in txt or '半' in txt:
        attrs.append(t)
    elif re.match(r'^[A-Za-z]+.*?\d+', txt) or re.match(r'^\d+$', txt):
        boxes.append(t)

print(f"Found {len(boxes)} boxes, {len(dims)} dimensions, {len(attrs)} attributes.")

# Group them by proximity to box
results = []
for b in boxes:
    bx, by = b['x'], b['y']
    
    # find nearest attr
    closest_attr = None
    min_dist = float('inf')
    for a in attrs:
        dist = math.hypot(a['x'] - bx, a['y'] - by)
        if dist < min_dist:
            min_dist = dist
            closest_attr = a
            
    # find nearest dims (find 2 closest dims)
    sorted_dims = sorted(dims, key=lambda d: math.hypot(d['x'] - bx, d['y'] - by))
    nearest_dims = sorted_dims[:2]
    
    results.append({
        'box': b['text'],
        'box_x': bx, 'box_y': by,
        'attr': closest_attr['text'] if closest_attr and min_dist < 500 else None,
        'attr_color': closest_attr['color'] if closest_attr and min_dist < 500 else None,
        'dims': [(d['text'], d['color']) for d in nearest_dims if math.hypot(d['x'] - bx, d['y'] - by) < 500]
    })

# output sample
with open('cad_filtered.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("Done. Partial results:")
for r in sorted(results, key=lambda x: x['box'])[:20]:
    print(r)
