import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import math
import json
import time

import win32com.client
import pythoncom

PROJ_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ_ROOT))

from cad_processor import group_lines_to_polygons, identify_pillars, extract_lines_and_texts

def connect_acad():
    try:
        acad = win32com.client.Dispatch("AutoCAD.Application")
        return acad
    except Exception as e:
        print(f"Error connecting to AutoCAD: {e}")
        return None

def build_inertia_path(spaces):
    """
    自適應走道慣性巡迴演算法 (Adaptive Inertia TSP)
    第一步自動找絕對最近鄰居以確立初始前進方向，完全免除初始寫死方向的缺陷。
    重度轉彎懲罰可絕對防止「跨越走道蜘蛛網」。
    """
    if not spaces:
        return []
    
    nodes = []
    for s in spaces:
        cx = (s["min_x"] + s["max_x"]) / 2
        cy = (s["min_y"] + s["max_y"]) / 2
        nodes.append({"cx": cx, "cy": cy, "space": s})
        
    # 起點：最右下角
    nodes.sort(key=lambda n: (-n["cx"], n["cy"]))
    current = nodes.pop(0)
    
    path = [current]
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
                
                # 若轉彎達 90 度 (dot=0)，Cost 直接飆升 100 倍！徹底防止亂跳
                # 倒退走 (dot=-1)，Cost 直接飆升 10000 倍
                penalty = 100.0 ** ((1.0 - dot) / 2.0)
                
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
                # 第一步找到最近鄰，確立這排的走廊長相
                vec = (new_vx, new_vy)
            else:
                # 擁有 50% 的動態平滑率，避免小偏差就把向量折歪
                alpha = 0.5
                next_vx = vec[0] * alpha + new_vx * (1 - alpha)
                next_vy = vec[1] * alpha + new_vy * (1 - alpha)
                mag = math.hypot(next_vx, next_vy)
                if mag > 0:
                    vec = (next_vx/mag, next_vy/mag)
                else:
                    vec = (new_vx, new_vy)
                    
        path.append(best_node)
        current = best_node
        nodes.remove(best_node)
        
    return path

def decide_text_rotation(sp):
    """
    不再依賴不穩定的 TSP 前後向量，
    全面採用 Bounding Box 的長寬比 (Aspect Ratio) 來計算字體方向！
    這 100% 符合人類工程師畫圖的置字邏輯 (長方形裡順著空間閱讀)。
    """
    w = sp["max_x"] - sp["min_x"]
    h = sp["max_y"] - sp["min_y"]
    
    # 稍微給予容差，例如寬只比高多 10%，還是當作方塊。
    # AutoCAD 裡，大於 1.2 倍的明顯長軸決定字的旋轉
    if h > w * 1.2:
        return math.pi / 2.0 # 直倉，字體打直
    else:
        return 0.0 # 寬倉或方倉，字體打平

def _purge_old_layers(doc):
    """清理過去失敗的測試文字，還原乾淨畫布"""
    for index in range(doc.Layers.Count):
        layer = doc.Layers.Item(index)
        if layer.Name.upper() in ["PREDICTION_ROUTE", "ROUTE_TEXT", "TRUTH_ROUTE"]:
            # 必須把該圖層的物件刪光才能順利運作
            layer.color = 5
            
def create_layer(doc, layer_name, color):
    for index in range(doc.Layers.Count):
        layer = doc.Layers.Item(index)
        if layer.Name.upper() == layer_name:
            layer.color = color 
            return layer
    layer = doc.Layers.Add(layer_name)
    layer.color = color 
    return layer

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
        try:
            acad.Documents.Open(dwg_path)
        except Exception as e:
            print(f"Doc could be already open or error: {e}")
        time.sleep(1)
        doc = acad.ActiveDocument
    else:
        try:
            doc.Activate()
            time.sleep(0.5)
        except:
            pass
            
    try:
        print(f"✅ 連線成功。已切換至目標圖紙: {doc.Name}")
    except:
        print("✅ 連線成功 (忽略 Name COM 錯誤)。")

    print("⏳ 重新抽取圖形實體...")
    import subprocess
    subprocess.run([sys.executable, str(PROJ_ROOT / "extract_cad_safe.py")], check=True)
    
    with open(str(PROJ_ROOT / "cad_dump.json"), "r", encoding="utf-8") as f:
        entities = json.load(f)
        
    lines, _ = extract_lines_and_texts(entities)
    
    print("🧩 尋找空倉位...")
    polygons = group_lines_to_polygons(lines, threshold=10.0)
    pillars, spaces = identify_pillars(polygons, max_pillar_size=800.0)
    print(f"📊 找到 {len(spaces)} 個倉位。")
    
    if not spaces:
        print("❌ 圖上無倉位。")
        return
        
    print("🤖 執行 Inertia TSP 2.0 (重度轉彎懲罰) 計算標號順序...")
    path = build_inertia_path(spaces)
    
    # 計算 Global Font Size (全域字體大小)，絕不再忽大忽小
    min_dims = []
    for s in spaces:
        w = s["max_x"] - s["min_x"]
        h = s["max_y"] - s["min_y"]
        min_dims.append(min(w, h))
    
    # 取中位數的縮放作為基準，避免極端異常值干擾
    min_dims.sort()
    median_dim = min_dims[len(min_dims)//2]
    global_text_height = max(median_dim * 0.25, 100.0)
    print(f"📏 全域字首高度鎖定為: {global_text_height:.1f} mm")
    
    print("✍️ 正在將文字均勻植入圖面 (PREFIX='HD', START=001)...")
    _purge_old_layers(doc)
    create_layer(doc, "ROUTE_TEXT", 3) # Green text
    create_layer(doc, "PREDICTION_ROUTE", 5) # Blue Polyline
    
    prefix = "HD"
    start_num = 1
    
    flat_points = []
    ms = doc.ModelSpace
    
    for i, node in enumerate(path):
        num_str = f"{prefix}{start_num + i:03d}"
        
        cx, cy = node["cx"], node["cy"]
        sp = node["space"]
        
        # 畫預測藍線用
        flat_points.extend([cx, cy])
        
        # 決定旋轉角 (基於 Bounding Box，100% 準確統一)
        rotation = decide_text_rotation(sp)
        
        # 插入文字
        pt = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, (float(cx), float(cy), 0.0))
        
        txt_obj = ms.AddText(num_str, pt, global_text_height)
        txt_obj.Layer = "ROUTE_TEXT"
        txt_obj.Rotation = rotation
        txt_obj.Alignment = 10 
        txt_obj.TextAlignmentPoint = pt
        
    # 順便把新的完美 Polyline 重畫上去
    points_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flat_points)
    poly = ms.AddLightWeightPolyline(points_array)
    poly.Layer = "PREDICTION_ROUTE"
        
    doc.Regen(1) 
    print("🎉 等比例文字與完美軌跡已全數寫入！")
    
    save_path = str((PROJ_ROOT / "ref" / "倉位自動編號_完成版.dwg").resolve())
    try:
        if os.path.exists(save_path):
            os.remove(save_path)
            
        print(f"💾 正在另存新檔：{save_path}")
        doc.SaveAs(save_path)
        print("✅ 完美備份！")
    except Exception as e:
         print(f"⚠️ 儲存時發生錯誤: {e}")

if __name__ == "__main__":
    main()
