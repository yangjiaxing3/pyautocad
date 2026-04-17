import sys
import os
import json
from pathlib import Path
import win32com.client
import pythoncom

PROJ_ROOT = Path(__file__).resolve().parent.parent

def draw_truth_polyline():
    # 讀取 JSON
    json_path = PROJ_ROOT / "path_analysis_倉位含編號.json"
    if not json_path.exists():
        print(f"Error: 找不到真值檔 {json_path}")
        return
        
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    points = []
    for d in data:
        points.append(d["cx"])
        points.append(d["cy"])
        
    # 連線 AutoCAD
    acad = win32com.client.Dispatch("AutoCAD.Application")
    # 強制開啟該張圖紙
    dwg_path = str((PROJ_ROOT / "ref" / "倉位含編號.dwg").resolve())
    
    doc = None
    for i in range(acad.Documents.Count):
        d = acad.Documents.Item(i)
        if "倉位含編號" in d.Name:
            doc = d
            break
            
    if not doc:
        print(f"Opening {dwg_path}...")
        doc = acad.Documents.Open(dwg_path)
    
    doc.Activate()
    print(f"Active Document: {doc.Name}")
    
    # 建立真理紅線圖層
    layer_name = "TRUTH_ROUTE"
    layer = None
    for i in range(doc.Layers.Count):
        l = doc.Layers.Item(i)
        if l.Name == layer_name:
            layer = l
            break
    if not layer:
        layer = doc.Layers.Add(layer_name)
    layer.color = 1 # Red
    
    # 將點繪製為 Polyline
    points_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, points)
    poly = doc.ModelSpace.AddLightWeightPolyline(points_array)
    poly.Layer = layer_name
    
    doc.Regen(1)
    print("✅ 成功繪製紅色真理線 (TRUTH_ROUTE)！")

if __name__ == "__main__":
    draw_truth_polyline()
