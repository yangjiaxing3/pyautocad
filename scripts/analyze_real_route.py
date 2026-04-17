import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import json
import win32com.client
import pythoncom

PROJ_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ_ROOT))

from extract_cad_safe import get_cad_data
from cad_processor import extract_lines_and_texts, group_lines_to_polygons, identify_pillars, bind_texts_to_spaces
from main_pipeline import _categorize_texts

def open_acad_doc(doc_path):
    acad = win32com.client.Dispatch("AutoCAD.Application")
    acad.Visible = True
    
    # Check if already open
    for i in range(acad.Documents.Count):
        doc = acad.Documents.Item(i)
        if doc.Name.lower() == Path(doc_path).name.lower():
            doc.Activate()
            return acad, doc
            
    # Open doc
    doc = acad.Documents.Open(str(doc_path))
    return acad, doc

def analyze_real_path(dwg_name):
    dwg_path = PROJ_ROOT / "ref" / dwg_name
    print(f"Opening: {dwg_path}")
    acad, doc = open_acad_doc(dwg_path)
    
    # Dump using the script's logic roughly
    print("Dumping entities from ActiveDocument (subprocess)...")
    import subprocess
    subprocess.run([sys.executable, str(PROJ_ROOT / "extract_cad_safe.py")], check=True)
    
    with open(str(PROJ_ROOT / "cad_dump.json"), "r", encoding="utf-8") as f:
        entities = json.load(f)
    
    print(f"Processing {len(entities)} entities...")
    lines, texts = extract_lines_and_texts(entities)
    boxes, dims, attrs = _categorize_texts(texts)
    
    polygons = group_lines_to_polygons(lines, threshold=10.0)
    pillars, spaces = identify_pillars(polygons, max_pillar_size=800.0)
    
    # 綁定文字到空間
    bindings = bind_texts_to_spaces(boxes, spaces)
    
    # 建立正式的空間序列
    numbered_spaces = []
    for i, texts_in_space in bindings.items():
        if not texts_in_space:
            continue
        # 取第一個字串並去除前綴，只保留數字
        txt = texts_in_space[0].get("text", "")
        # 解析數字
        import re
        match = re.search(r'\d+', txt)
        if match:
            num = int(match.group())
            space = spaces[i]
            cx = (space["min_x"] + space["max_x"]) / 2
            cy = (space["min_y"] + space["max_y"]) / 2
            numbered_spaces.append({"num": num, "cx": cx, "cy": cy, "raw": txt})
            
    # 依照編號排序
    numbered_spaces.sort(key=lambda x: x["num"])
    
    print(f"Extracted {len(numbered_spaces)} numbered spaces.")
    print("Path sequence (first 10):")
    for s in numbered_spaces[:10]:
        print(f"[{s['num']}] txt:{s['raw']} -> ({s['cx']:.1f}, {s['cy']:.1f})")
        
    print("Path sequence (last 10):")
    for s in numbered_spaces[-10:]:
        print(f"[{s['num']}] txt:{s['raw']} -> ({s['cx']:.1f}, {s['cy']:.1f})")
        
    # 將結果輸出供 AI 分析
    out_path = PROJ_ROOT / f"path_analysis_{Path(dwg_name).stem}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(numbered_spaces, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    analyze_real_path("倉位含編號.dwg")
