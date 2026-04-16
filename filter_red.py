import json

with open('red_geoms.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

lines = [g for g in data['geoms'] if g['type'] == 'line']
if not lines:
    print("No red lines found.")
else:
    min_x = min(min(l['x1'], l['x2']) for l in lines)
    max_x = max(max(l['x1'], l['x2']) for l in lines)
    min_y = min(min(l['y1'], l['y2']) for l in lines)
    max_y = max(max(l['y1'], l['y2']) for l in lines)
    print(f"Red bounds: X({min_x:.1f} to {max_x:.1f}), Y({min_y:.1f} to {max_y:.1f})")

    # Let's see how many HD texts are inside bounding boxes formed by these lines
    # A realistic grid is formed by intersecting lines. Let's just find texts inside the global bounding box first
    texts = [t for t in data['texts'] if 'HD' in t['text'].upper() and min_x - 100 <= t['x'] <= max_x + 100 and min_y - 100 <= t['y'] <= max_y + 100]
    print('HD texts globally in red area:', sorted([t['text'] for t in texts]))

    # Now let's print ALL HD texts we extracted originally in cad_dump
    original_data = json.load(open('cad_dump.json', encoding='utf-8'))
    all_hds = [d['text'] for d in original_data if 'text' in d and 'HD' in d['text'].upper()]
    # are they in the red zone?
    in_red_zone = [t for t in all_hds if t in [tx['text'] for tx in texts]]
    out_of_red_zone = [t for t in all_hds if t not in in_red_zone]
    print(f"Total HDs: {len(all_hds)}, In red zone: {len(in_red_zone)}, Out of red zone: {len(out_of_red_zone)}")

    # Is the user talking about cell lines? Let's check text color again.
    # User: "在倉位（紅色格子）裡的 'HD***' 是倉位號碼"
