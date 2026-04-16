import json

with open('red_geoms.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

lines = [g for g in data['geoms'] if g['type'] == 'line']

# Identify the 6 rectangles from 24 lines
# A simplistic way: just group lines by proximity or just treat each line as part of a bounding box for texts.
# Actually, let's just create connected components of lines

def point_dist(p1, p2):
    return ((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)**0.5

components = []
for l in lines:
    added = False
    for comp in components:
        for cl in comp:
            if point_dist((l['x1'], l['y1']), (cl['x1'], cl['y1'])) < 10 or \
               point_dist((l['x1'], l['y1']), (cl['x2'], cl['y2'])) < 10 or \
               point_dist((l['x2'], l['y2']), (cl['x1'], cl['y1'])) < 10 or \
               point_dist((l['x2'], l['y2']), (cl['x2'], cl['y2'])) < 10:
                comp.append(l)
                added = True
                break
        if added:
            break
    if not added:
        components.append([l])

# merge components that might touch
merged = True
while merged:
    merged = False
    new_components = []
    while components:
        curr = components.pop(0)
        has_merged = False
        for i, other in enumerate(components):
            touch = False
            for l1 in curr:
                for l2 in other:
                    if point_dist((l1['x1'], l1['y1']), (l2['x1'], l2['y1'])) < 10 or \
                       point_dist((l1['x1'], l1['y1']), (l2['x2'], l2['y2'])) < 10 or \
                       point_dist((l1['x2'], l1['y2']), (l2['x1'], l2['y1'])) < 10 or \
                       point_dist((l1['x2'], l1['y2']), (l2['x2'], l2['y2'])) < 10:
                        touch = True
                        break
                if touch: break
            if touch:
                other.extend(curr)
                has_merged = True
                merged = True
                break
        if not has_merged:
            new_components.append(curr)
    components = new_components

print(f"Found {len(components)} red components (boxes).")

boxes_bounds = []
for i, comp in enumerate(components):
    min_x = min(min(l['x1'], l['x2']) for l in comp)
    max_x = max(max(l['x1'], l['x2']) for l in comp)
    min_y = min(min(l['y1'], l['y2']) for l in comp)
    max_y = max(max(l['y1'], l['y2']) for l in comp)
    boxes_bounds.append((min_x, max_x, min_y, max_y))
    print(f" Box {i+1}: X({min_x:.1f} to {max_x:.1f}), Y({min_y:.1f} to {max_y:.1f})")

# Check texts inside each component
original_data = json.load(open('cad_dump.json', encoding='utf-8'))
all_hds = [d for d in original_data if 'text' in d and 'HD' in d['text'].upper()]

valid_boxes = []
for hd in all_hds:
    # is it strictly inside any of the red boxes?
    for bx in boxes_bounds:
        # Give a little tolerance
        if bx[0]-50 <= hd['x'] <= bx[1]+50 and bx[2]-50 <= hd['y'] <= bx[3]+50:
            valid_boxes.append(hd['text'])
            break

print("HD*** strictly inside RED BOXES:", sorted(valid_boxes))
