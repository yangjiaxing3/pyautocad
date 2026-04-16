import win32com.client
import json
import os
import time

def get_cad_data():
    try:
        acad = win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception as e:
        print("Failed to get AutoCAD object:", e)
        return

    doc = None
    try:
        doc = acad.ActiveDocument
        print("Initial Document:", doc.Name)
    except Exception as e:
        print("No ActiveDocument found, trying to open Drawing3.dwg")

    file_path = os.path.abspath(r"C:\Users\yang3\Documents\GitHub\pyautocad\ref\Drawing3.dwg")
    
    # Check if doc is not Drawing3
    if not doc or "Drawing3" not in doc.Name:
        print("Opening", file_path)
        try:
            doc = acad.Documents.Open(file_path)
            time.sleep(2)
        except Exception as e:
            print("Failed to open file:", e)
            return

    try:
        doc = acad.ActiveDocument
        print("Active Document is now:", doc.Name)
    except Exception as e:
        print("Failed to get ActiveDocument after open:", e)
        return

    try:
        model = doc.ModelSpace
    except Exception as e:
        print("Failed to get ModelSpace:", e)
        return

    entities = []
    
    count = model.Count
    print("Total entities in ModelSpace:", count)
    
    for i in range(count):
        try:
            entity = model.Item(i)
            ent_type = entity.ObjectName
            
            # We are interested in Text, MText, and possibly Lines/Polylines (for pink arrows)
            if ent_type in ['AcDbText', 'AcDbMText', 'AcDbBlockReference', 'AcDbLine', 'AcDbPolyline', 'AcDbLeader']:
                ent_data = {
                    'type': ent_type,
                    'color': entity.Color
                }
                
                # TrueColor value (if object uses TrueColor)
                try:
                    true_color = entity.TrueColor
                    ent_data['color_rgb'] = [true_color.Red, true_color.Green, true_color.Blue]
                except:
                    pass

                if ent_type in ['AcDbText', 'AcDbMText']:
                    ent_data['text'] = entity.TextString
                    ent_data['x'] = entity.InsertionPoint[0]
                    ent_data['y'] = entity.InsertionPoint[1]
                    ent_data['rotation'] = getattr(entity, 'Rotation', 0)
                elif ent_type == 'AcDbLine':
                    ent_data['start'] = [entity.StartPoint[0], entity.StartPoint[1]]
                    ent_data['end'] = [entity.EndPoint[0], entity.EndPoint[1]]
                elif ent_type == 'AcDbBlockReference':
                    ent_data['name'] = entity.Name
                    ent_data['x'] = entity.InsertionPoint[0]
                    ent_data['y'] = entity.InsertionPoint[1]
                
                entities.append(ent_data)
        except Exception as e:
            pass

    with open('cad_dump.json', 'w', encoding='utf-8') as f:
        json.dump(entities, f, ensure_ascii=False, indent=2)
    print(f"Dumped {len(entities)} entities to cad_dump.json")

if __name__ == "__main__":
    get_cad_data()
