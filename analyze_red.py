import win32com.client
import json

def get_cad_layers():
    acad = win32com.client.GetActiveObject("AutoCAD.Application")
    doc = acad.ActiveDocument
    
    layers_data = {}
    for i in range(doc.Layers.Count):
        lyr = doc.Layers.Item(i)
        layers_data[lyr.Name] = lyr.Color
        
    print(f"Total layers: {len(layers_data)}")
    for k, v in layers_data.items():
        if v == 1: # Red
            print("RED LAYER:", k)

    # Let's also check objects to find bounding boxes on RED layers
    model = doc.ModelSpace
    count = model.Count
    red_boxes = []
    
    for i in range(count):
        try:
            ent = model.Item(i)
            # if ent.Color == 1 or (ent.Color == 256 and layers_data.get(ent.Layer) == 1):
            if ent.Layer in layers_data and layers_data[ent.Layer] == 1:
                # it's on a red layer
                # mostly want to see what types they are
                red_boxes.append({
                    "type": ent.ObjectName,
                    "layer": ent.Layer,
                    "color": ent.Color
                })
        except:
            pass
            
    print(f"Total red layer objects: {len(red_boxes)}")
    import collections
    print("Red obj types:", collections.Counter([b['type'] for b in red_boxes]))

if __name__ == "__main__":
    get_cad_layers()
