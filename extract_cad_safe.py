import win32com.client
import json
import sys

def get_cad_data():
    print("Connecting to AutoCAD...", flush=True)
    try:
        acad = win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception as e:
        print("Failed to get AutoCAD object:", e, flush=True)
        return

    print("Iterating over open documents...", flush=True)
    target_doc = None
    try:
        for i in range(acad.Documents.Count):
            doc = acad.Documents.Item(i)
            print("Found doc:", doc.Name, flush=True)
            if "Drawing3" in doc.Name:
                target_doc = doc
                break
    except Exception as e:
        print("Failed to iterate documents:", e, flush=True)
        return

    if not target_doc:
        print("Drawing3.dwg is not open. Currently active doc is:", flush=True)
        try:
            print(acad.ActiveDocument.Name, flush=True)
            target_doc = acad.ActiveDocument
            print("Will use active document instead.", flush=True)
        except:
            print("No active document.", flush=True)
            return

    try:
        model = target_doc.ModelSpace
    except Exception as e:
        print("Failed to get ModelSpace:", e, flush=True)
        return

    entities = []
    
    count = model.Count
    print("Total entities in ModelSpace:", count, flush=True)
    
    for i in range(count):
        try:
            entity = model.Item(i)
            ent_type = entity.ObjectName
            
            if ent_type in ['AcDbText', 'AcDbMText', 'AcDbBlockReference', 'AcDbLine', 'AcDbPolyline', 'AcDbLeader']:
                ent_data = {
                    'type': ent_type,
                    'color': entity.Color
                }
                
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
    print(f"Dumped {len(entities)} entities to cad_dump.json", flush=True)

if __name__ == "__main__":
    get_cad_data()
