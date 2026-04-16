import win32com.client
import json
import math

def get_boxes():
    acad = win32com.client.GetActiveObject("AutoCAD.Application")
    doc = acad.ActiveDocument
    model = doc.ModelSpace
    
    # 1. Identify which layers are red
    red_layers = [doc.Layers.Item(i).Name for i in range(doc.Layers.Count) if doc.Layers.Item(i).Color == 1]
    
    # 2. Extract lines/polylines that are RED (either layer color is red and object is ByLayer, or object is Red)
    red_geoms = []
    texts = []
    
    for i in range(model.Count):
        try:
            ent = model.Item(i)
            # AcDbText
            if ent.ObjectName == 'AcDbText':
                texts.append({
                    'text': ent.TextString,
                    'x': ent.InsertionPoint[0],
                    'y': ent.InsertionPoint[1],
                    'color': ent.Color
                })
            # Lines / Polylines
            elif ent.ObjectName in ['AcDbLine', 'AcDbPolyline', 'AcDb2dPolyline']:
                # check if red
                is_red = False
                if ent.Color == 1:
                    is_red = True
                elif ent.Color == 256 and ent.Layer in red_layers: # ByLayer
                    is_red = True
                # If true color red
                if not is_red:
                    try:
                        if ent.TrueColor.Red == 255 and ent.TrueColor.Green == 0 and ent.TrueColor.Blue == 0:
                            is_red = True
                    except:
                        pass
                
                if is_red:
                    if ent.ObjectName == 'AcDbLine':
                        red_geoms.append({
                            'type': 'line',
                            'x1': ent.StartPoint[0], 'y1': ent.StartPoint[1],
                            'x2': ent.EndPoint[0], 'y2': ent.EndPoint[1]
                        })
                    else: # Polyline
                        coords = ent.Coordinates
                        pts = []
                        for j in range(0, len(coords)-1, 2): # 2D lightweight polyline
                            pts.append((coords[j], coords[j+1]))
                        red_geoms.append({
                            'type': 'poly',
                            'pts': pts
                        })
        except Exception as e:
            pass

    print(f"Extracted {len(red_geoms)} red geometries, {len(texts)} texts.")
    
    # 3. Find HD*** texts that are actually inside or very close to these red geometries
    # Actually, let's just dump ALL red geometries to see where they are
    with open('red_geoms.json', 'w') as f:
        json.dump({'geoms': red_geoms, 'texts': texts}, f)

if __name__ == '__main__':
    get_boxes()
