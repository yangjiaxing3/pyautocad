import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path
import math

import win32com.client
import pythoncom

# Ensure pyautocad lib path is valid
PROJ_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ_ROOT))

from cad_processor import group_lines_to_polygons, identify_pillars, extract_lines_and_texts

def connect_acad():
    try:
        acad = win32com.client.Dispatch("AutoCAD.Application")
        # To avoid dialogs
        return acad
    except Exception as e:
        print(f"Error connecting to AutoCAD: {e}")
        return None

def create_route_layer(doc):
    """創建或取得 PREDICTION_ROUTE 圖層並設為藍色"""
    for index in range(doc.Layers.Count):
        layer = doc.Layers.Item(index)
        if layer.Name.upper() == "PREDICTION_ROUTE":
            layer.color = 5  # 5 = Blue
            return layer
            
    # 沒有則新建
    layer = doc.Layers.Add("PREDICTION_ROUTE")
    layer.color = 5  # 5 = Blue
    return layer

def build_inertia_path(spaces):
    """
    走道慣性巡迴演算法 (Inertia TSP)
    保持直線前進，遇到底部才轉彎。
    """
    if not spaces:
        return []
    
    nodes = []
    for s in spaces:
        cx = (s["min_x"] + s["max_x"]) / 2
        cy = (s["min_y"] + s["max_y"]) / 2
        nodes.append({"cx": cx, "cy": cy, "space": s})
        
    # 起點：我們取「原本真值圖中的左上或右上？」
    # 根據真理 json，起點 HD1 座標是 (47738.8, 24102.1) -> 相對較大的 X 與中間的 Y
    # 這裡我們通用採用最右下角起點 (X最大, Y最小)
    nodes.sort(key=lambda n: (-n["cx"], n["cy"]))
    current = nodes.pop(0)
    
    path = [(current["cx"], current["cy"])]
    vec = (0, 0)
    
    while nodes:
        best_node = None
        best_cost = float('inf')
        
        for n in nodes:
            dx = n["cx"] - current["cx"]
            dy = n["cy"] - current["cy"]
            dist = math.hypot(dx, dy)
            
            penalty = 1.0
            if vec != (0, 0) and dist > 0:
                ux, uy = dx/dist, dy/dist
                vx, vy = vec
                dot = ux*vx + uy*vy
                # dot 落在 [-1, 1]。越大代表方向越一致
                # 以 10 為底的指數放大差異：同向(1) cost * 1, 反向(-1) cost * 10
                penalty = 10.0 ** ((1.0 - dot) / 2.0)
                
            # 計算花費：距離平方以強化尋找「最近距離」的權重，再乘上方向懲罰
            cost = (dist ** 2) * penalty
            
            if cost < best_cost:
                best_cost = cost
                best_node = n
                
        # 更新向量與點
        dx = best_node["cx"] - current["cx"]
        dy = best_node["cy"] - current["cy"]
        dist = math.hypot(dx, dy)
        
        if dist > 0:
            new_vx, new_vy = dx/dist, dy/dist
            if vec == (0, 0):
                vec = (new_vx, new_vy)
            else:
                # 慣性平滑：80% 採用新方向，20% 保留舊方向，避免直角轉彎立刻喪失原本直行慣性
                alpha = 0.2
                next_vx = vec[0] * alpha + new_vx * (1 - alpha)
                next_vy = vec[1] * alpha + new_vy * (1 - alpha)
                mag = math.hypot(next_vx, next_vy)
                if mag > 0:
                    vec = (next_vx/mag, next_vy/mag)
                else:
                    vec = (new_vx, new_vy)
                    
        path.append((best_node["cx"], best_node["cy"]))
        current = best_node
        nodes.remove(best_node)
        
    return path

# old build_snake_path function removed fully

def main():
    acad = connect_acad()
    if not acad:
        return
        
    dwg_path = str((PROJ_ROOT / "ref" / "倉位不含編號.dwg").resolve())
    doc = None
    for i in range(acad.Documents.Count):
        d = acad.Documents.Item(i)
        if "倉位不含編號" in d.Name:
            doc = d
            break
            
    if not doc:
        print(f"Opening {dwg_path}...")
        acad.Documents.Open(dwg_path)
        doc = acad.ActiveDocument
    else:
        doc.Activate()
        
    print(f"✅ 連線成功。已強制切換至目標圖紙: {doc.Name}")

    # 1. 抽取實體
    print("⏳ 正在取得所有圖形實體...")
    import subprocess
    subprocess.run([sys.executable, str(PROJ_ROOT / "extract_cad_safe.py")], check=True)
    
    import json
    with open(str(PROJ_ROOT / "cad_dump.json"), "r", encoding="utf-8") as f:
        entities = json.load(f)
        
    lines, _ = extract_lines_and_texts(entities)
    
    # 2. 空間縫合
    print("🧩 正在運算空間方塊...")
    polygons = group_lines_to_polygons(lines, threshold=10.0)
    pillars, spaces = identify_pillars(polygons, max_pillar_size=800.0)
    print(f"📊 找到 {len(spaces)} 個倉位。")
    
    if not spaces:
        print("❌ 圖上無倉位。")
        return
        
    # 3. 排序與產出節點
    print("🐍 正在規劃具備動線慣性的人工智慧走訪路徑 (Inertia TSP)...")
    path_nodes = build_inertia_path(spaces)
    
    # 4. 準備陣列給 COM 呼叫
    flat_points = []
    for (x, y) in path_nodes:
        flat_points.extend([x, y])
        
    if len(flat_points) < 4:
         print("❌ 倉位過少無法成線。")
         return
         
    # 5. AutoCAD 畫圖
    print("✒️ 正在寫入 AutoCAD (繪製藍色預測線)...")
    create_route_layer(doc)
    
    points_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flat_points)
    
    poly = doc.ModelSpace.AddLightWeightPolyline(points_array)
    poly.Layer = "PREDICTION_ROUTE"
    
    # Optional: Highlight polyline or regen
    doc.Regen(1) 
    print("🎉 動線已成功繪製！")
    
    # 6. 自動存檔為 Template
    save_path = str((PROJ_ROOT / "ref" / "倉位自動編號_Polyline示範樣板.dwg").resolve())
    try:
        # SaveAs parameter 1 is filename
        # parameter 2: Type (try to save as current version)
        import os
        if os.path.exists(save_path):
            os.remove(save_path)
            
        print(f"💾 正在另存新檔：{save_path}")
        doc.SaveAs(save_path)
        print("✅ 儲存完畢。")
    except Exception as e:
         print(f"⚠️ 儲存時發生錯誤: {e}")

if __name__ == "__main__":
    main()
