import json
import re
import math
import pandas as pd
import os

# Load CAD data
data = json.load(open('cad_dump.json', encoding='utf-8'))

texts = []
for d in data:
    if 'text' in d:
        t = d['text'].strip()
        if t:
            texts.append(d)

# Categorize
boxes = []
dims = []
attrs = []

for t in texts:
    txt = t['text']
    if re.match(r'^\d+(\.\d+)?$', txt):
        dims.append(t)
    elif '單' in txt or '雙' in txt or '半' in txt:
        attrs.append(t)
    elif re.match(r'^[A-Za-z]+.*?\d+', txt) or re.match(r'^\d+$', txt): # e.g. WU 112, HD102
        if len(txt) <= 8:  # avoid long arbitrary texts
            boxes.append(t)

# Default Rules dictionary based on the prompt
# color -> (Type, H)
COLOR_MAPPING = {
    3: ('單', 2.3),   # Green
    8: ('單', 2.0),   # Gray (might also be 251/250 etc in true color indexing, we will fallback)
    251: ('單', 2.0), # Gray
    6: ('半', 2.8),   # Purple/Magenta
    5: ('雙', 3.2),   # Dark blue
    4: ('雙', 3.3),   # Cyan/Water blue
    2: ('雙', 3.4),   # Yellow
    30: ('雙', 3.6),  # Orange
    7: ('雙', 4.0),   # White
    0: ('雙', 4.0),   # White/ByBlock
    256: ('雙', 4.0)  # White/ByLayer
}

def format_box_num(text):
    # Zero pad the digits to 3 digits minimum
    def pad_num(match):
        return match.group(1).zfill(3)
    return re.sub(r'(\d+)', pad_num, text)

results = []
for b in boxes:
    bx, by = b['x'], b['y']
    
    # closest attr
    closest_attr = None
    min_dist = float('inf')
    for a in attrs:
        dist = math.hypot(a['x'] - bx, a['y'] - by)
        if dist < min_dist:
            min_dist = dist
            closest_attr = a
            
    # nearest dims
    sorted_dims = sorted(dims, key=lambda d: math.hypot(d['x'] - bx, d['y'] - by))
    nearest_dims = sorted_dims[:2]
    
    # determine W and D
    W = None
    D = None
    for d in nearest_dims:
        if math.hypot(d['x'] - bx, d['y'] - by) > 800: # Threshold distance
            continue
            
        val = float(d['text']) / 1000.0 # CAD is usually in mm, convert to meters
        val = round(val, 2)
        
        if d['color'] == 2: # Yellow is Width
            W = val
        else:
            D = val
            
    # if we have two dims but none is yellow, default to the first as W, second as D
    if W is None and len(nearest_dims) >= 1:
        W = round(float(nearest_dims[0]['text']) / 1000.0, 2)
    if D is None and len(nearest_dims) >= 2:
        D = round(float(nearest_dims[1]['text']) / 1000.0, 2)
        
    # determine Type and H
    attr_type = ""
    H = ""
    
    # check closest attribute box distance to see if it belongs to this box
    if closest_attr and min_dist < 500:
        c = closest_attr['color']
        if c in COLOR_MAPPING:
            attr_type, H = COLOR_MAPPING[c]
        else:
            attr_type, H = '單', 2.3 # fallback

    # if no attribute nearby, we could rely on box color if it inherited layer color?
    if not attr_type:
        c = b['color']
        if c in COLOR_MAPPING:
            attr_type, H = COLOR_MAPPING[c]

    # Only append if we got decent data
    if W is not None and D is not None:
        results.append({
            '倉位號碼': format_box_num(b['text']),
            '屬性': attr_type,
            'W': W,
            'D': D,
            'H': H
        })

# Sort by 倉位號碼 
results.sort(key=lambda x: x['倉位號碼'])

# output Excel
output_path = os.path.abspath(r'C:\Users\yang3\Documents\GitHub\pyautocad\ref\Drawing3_抽出結果.xlsx')
df = pd.DataFrame(results)

# If there are exact duplicate rows, drop them
df = df.drop_duplicates()

df.to_excel(output_path, index=False)
print(f"Excel generated at: {output_path}")
