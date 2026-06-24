import sys
import os
import json
import traceback
import pythoncom
import win32com.client

# 加入父目錄以便載入模組
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main_pipeline import run_pipeline, results_to_excel_bytes

import time

# NOTE: 使用統一的 COM 重試防禦層，避免重複實作脆弱的重試邏輯。
# extract_entities_safe 內建了對 RPC_E_CALL_REJECTED 的指數退避保護。
from com_retry import extract_entities_safe


def extract_entities(doc):
    """
    從 AutoCAD Document 提取實體。
    委託給 com_retry.extract_entities_safe，提供統一的 COM 防禦。
    """
    # Retry logic for ModelSpace
    model = None
    for _ in range(5):
        try:
            model = doc.ModelSpace
            break
        except Exception as e:
            time.sleep(2)

    if model is None:
        raise Exception("Failed to access ModelSpace after multiple retries")

    return extract_entities_safe(doc, max_retries=10, base_delay=1.0)


def main():
    if len(sys.argv) < 3:
        print("Usage: python auto_cad_worker.py <in_dwg> <out_dwg>")
        sys.exit(1)
        
    in_dwg = os.path.abspath(sys.argv[1])
    out_dwg = os.path.abspath(sys.argv[2])
    
    pythoncom.CoInitialize()
    try:
        try:
            acad = win32com.client.dynamic.Dispatch("AutoCAD.Application")
        except:
            acad = win32com.client.Dispatch("AutoCAD.Application")
            
        # --- [防禦性：抑制 AutoCAD 擾人的彈出視窗] ---
        try:
            try:
                temp_doc = acad.ActiveDocument
            except:
                temp_doc = acad.Documents.Add()
            temp_doc.SetVariable("PROXYNOTICE", 0)
            temp_doc.SetVariable("FONTALT", "simplex.shx")
            temp_doc.SetVariable("FILEDIA", 0)
            temp_doc.SetVariable("CMDDIA", 0)
        except:
            pass
        # ----------------------------------------------

        doc = None
        for _ in range(5):
            try:
                doc = acad.Documents.Open(in_dwg, False)
                break
            except Exception as e:
                time.sleep(2)
                
        if doc is None:
            raise Exception("Failed to open document after multiple retries")
            
        try:
            # 等待 AutoCAD 完成載入
            time.sleep(2)
        
            # 1. 提取實體
            entities = extract_entities(doc)
            if not entities:
                print("ERROR: No entities found in DWG.")
                sys.exit(1)
            
            # 2. 跑 Pipeline
            exclude = ["004", "013", "044", "444", "4444"]
            # 此處寫死 prefix = "HD", 也可改成由外部參數傳入
            prefix = "HD"
            results = run_pipeline(entities, prefix=prefix, start_num=500, exclude_list=exclude)
        
            # Generate Excel report
            try:
                eb = results_to_excel_bytes(results)
                with open(out_dwg.replace(".dwg", ".xlsx"), "wb") as f:
                    f.write(eb)
            except Exception as e:
                print("EXCEL EXPORT ERROR:", e)
        
            # 3. Ray Cast 找中心點
            lines = []
            for ent in entities:
                if ent.get("type") == "AcDbLine":
                    lines.append(ent)
                elif ent.get("type") == "AcDbPolyline" and "ROUTE" not in str(ent.get("layer", "")).upper():
                    verts = ent.get("vertices", [])
                    for i in range(len(verts)-1):
                        lines.append({
                            "start_x": verts[i][0], "start_y": verts[i][1],
                            "end_x": verts[i+1][0], "end_y": verts[i+1][1],
                        })
                    
            h_lines = []
            v_lines = []
            for l in lines:
                if "start_x" not in l: continue
                sx, sy, ex, ey = l["start_x"], l["start_y"], l["end_x"], l["end_y"]
                if abs(sy - ey) < 1.0: h_lines.append(l)
                if abs(sx - ex) < 1.0: v_lines.append(l)
            
            tol = 150
            for r in results:
                ax, ay = r.get("cx"), r.get("cy")
                if ax is None: continue
            
                top_y = bot_y = right_x = left_x = None
            
                for l in h_lines:
                    sx, ex, sy = l["start_x"], l["end_x"], l["start_y"]
                    if min(sx, ex) - tol <= ax <= max(sx, ex) + tol:
                        if sy > ay and (top_y is None or sy < top_y): top_y = sy
                        if sy < ay and (bot_y is None or sy > bot_y): bot_y = sy
                    
                for l in v_lines:
                    sy, ey, sx = l["start_y"], l["end_y"], l["start_x"]
                    if min(sy, ey) - tol <= ay <= max(sy, ey) + tol:
                        if sx > ax and (right_x is None or sx < right_x): right_x = sx
                        if sx < ax and (left_x is None or sx > left_x): left_x = sx
                        
                if top_y and bot_y and left_x and right_x:
                    w = right_x - left_x
                    h = top_y - bot_y
                    if 300 <= w <= 4000 and 300 <= h <= 4000:
                        r["final_x"] = (left_x + right_x)/2
                        r["final_y"] = (top_y + bot_y)/2
                    else:
                        r["final_x"] = ax
                        r["final_y"] = ay
                else:
                    r["final_x"] = ax
                    r["final_y"] = ay

            # 4. 寫入 AutoCAD
            model = doc.ModelSpace
            # 刪除舊的
            to_delete = []
            for i in range(model.Count):
                try:
                    e = model.Item(i)
                    if e.ObjectName in ["AcDbText", "AcDbMText"]:
                        txt = e.TextString
                        if txt.startswith(prefix) or (txt.isdigit() and len(txt) == 3):
                            to_delete.append(e)
                except: pass
            
            for e in to_delete:
                try: e.Delete()
                except: pass
            
            # 建立新圖層
            try:
                txt_layer = doc.Layers.Add("倉位編號")
                txt_layer.Color = 4
            except:
                pass

            # 寫入新的
            new_texts = []
            for r in results:
                raw_id = str(r["倉位號碼"])
                fx, fy = r.get("final_x"), r.get("final_y")
                if fx is not None and fy is not None:
                    pt = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, (fx, fy, 0.0))
                    text_obj = model.AddText(raw_id, pt, 150.0)
                    text_obj.Alignment = 10 
                    text_obj.TextAlignmentPoint = pt
                
                    try:
                        text_obj.Layer = "倉位編號"
                    except:
                        pass
                    
                    try:
                        text_obj.Color = 4 
                    except AttributeError:
                        try:
                            tc = text_obj.TrueColor
                            tc.SetRGB(0, 255, 255)
                            text_obj.TrueColor = tc
                        except Exception:
                            pass
                
                    new_texts.append(text_obj)
                
            # 將文字移至最上層 (Bring to front)
            try:
                dict_obj = model.GetExtensionDictionary()
                try:
                    sortents = dict_obj.GetObject("ACAD_SORTENTS")
                except:
                    sortents = dict_obj.AddObject("ACAD_SORTENTS", "AcDbSortentsTable")
            
                if new_texts:
                    objs_array = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, new_texts)
                    sortents.MoveToTop(objs_array)
            except Exception as e:
                pass # 如果失敗則依賴預設的創建順序 (最後建立的物件通常在最上層)
        
            # 5. 另存新檔
            # SaveAs requires absolute path, Format 64 = 2018 DWG
            doc.SaveAs(out_dwg, 64)
        finally:
            try:
                doc.Close(False)
            except:
                pass
        print("SUCCESS")
        
    except Exception as e:
        print(f"FATAL ERROR: {str(e)}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        pythoncom.CoUninitialize()

if __name__ == "__main__":
    main()
