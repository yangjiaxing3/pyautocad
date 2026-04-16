import math
import logging

logger = logging.getLogger(__name__)

def filter_excluded_texts(entities, exclude_list):
    """移除 exclude_list 中的文字"""
    result = []
    for ent in entities:
        if ent.get("type") in ["AcDbText", "AcDbMText"]:
            if ent.get("text") in exclude_list:
                continue
        result.append(ent)
    return result

def extract_lines_and_texts(entities):
    """分離線段與文字"""
    lines = []
    texts = []
    for ent in entities:
        if ent.get("type") == "AcDbLine":
            lines.append(ent)
        elif ent.get("type") in ["AcDbText", "AcDbMText"]:
            texts.append(ent)
    return lines, texts

def _distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def group_lines_to_polygons(lines, threshold=5.0):
    """Line Stitching 演算法，找出連通區域並產出 Bounding Box"""
    n = len(lines)
    parent = list(range(n))
    
    def find(i):
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]
        
    def union(i, j):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j
            
    # O(N^2) 判斷線段端點距離
    for i in range(n):
        for j in range(i + 1, n):
            si = lines[i]['start']
            ei = lines[i]['end']
            sj = lines[j]['start']
            ej = lines[j]['end']
            
            # 如果任一端點距離小於閾值
            if (_distance(si, sj) <= threshold or 
                _distance(si, ej) <= threshold or
                _distance(ei, sj) <= threshold or
                _distance(ei, ej) <= threshold):
                union(i, j)
                
    # 集合分組
    components = {}
    for i in range(n):
        r = find(i)
        if r not in components:
            components[r] = []
        components[r].append(lines[i])
        
    polygons = []
    for comp in components.values():
        xs = []
        ys = []
        for line in comp:
            xs.extend([line['start'][0], line['end'][0]])
            ys.extend([line['start'][1], line['end'][1]])
        if xs and ys:
            polygons.append({
                "min_x": min(xs),
                "max_x": max(xs),
                "min_y": min(ys),
                "max_y": max(ys)
            })
    return polygons

def identify_pillars(polygons, max_pillar_size=50):
    """過濾出尺寸小於 max_pillar_size 的多邊形作為柱子"""
    pillars = []
    spaces = []
    for poly in polygons:
        w = poly["max_x"] - poly["min_x"]
        h = poly["max_y"] - poly["min_y"]
        if w <= max_pillar_size and h <= max_pillar_size:
            pillars.append(poly)
        else:
            spaces.append(poly)
    return pillars, spaces

def _rect_intersect_area(r1, r2):
    """計算兩個 Bounding Box 的交集面積"""
    dx = min(r1["max_x"], r2["max_x"]) - max(r1["min_x"], r2["min_x"])
    dy = min(r1["max_y"], r2["max_y"]) - max(r1["min_y"], r2["min_y"])
    if dx > 0 and dy > 0:
        return dx * dy
    return 0

def bind_texts_to_spaces(texts, polygons):
    """
    將文字依照座標綁定到最近的空間 Bounding Box。
    回傳 dict: { polygon_index: [text_entity, ...] }
    """
    bindings = {i: [] for i in range(len(polygons))}

    for text in texts:
        tx = text.get("x", 0)
        ty = text.get("y", 0)

        best_idx = -1
        best_dist = float("inf")

        for i, poly in enumerate(polygons):
            # 計算 Bounding Box 中心
            cx = (poly["min_x"] + poly["max_x"]) / 2
            cy = (poly["min_y"] + poly["max_y"]) / 2
            dist = _distance((tx, ty), (cx, cy))

            if dist < best_dist:
                best_dist = dist
                best_idx = i

        if best_idx >= 0:
            bindings[best_idx].append(text)

    return bindings

def calculate_net_dimensions(space_polygon, pillars_polygons):
    """扣除柱子面積，求得淨面積與長寬"""
    w = space_polygon["max_x"] - space_polygon["min_x"]
    d = space_polygon["max_y"] - space_polygon["min_y"]
    gross_area = w * d
    
    pillar_area = 0
    for p in pillars_polygons:
        pillar_area += _rect_intersect_area(space_polygon, p)
        
    return {
        "width": w,
        "depth": d,
        "gross_area": gross_area,
        "pillar_area": pillar_area,
        "net_area": gross_area - pillar_area
    }

def _closest_point_on_segment(p, a, b):
    # a, b are segment endpoints, p is point
    ax, ay = a
    bx, by = b
    px, py = p
    
    seg_dx = bx - ax
    seg_dy = by - ay
    
    seg_len2 = seg_dx**2 + seg_dy**2
    if seg_len2 == 0:
        return a, 0.0 # a == b
        
    t = ((px - ax) * seg_dx + (py - ay) * seg_dy) / seg_len2
    t = max(0, min(1, t))
    
    closest = (ax + t * seg_dx, ay + t * seg_dy)
    return closest, t

def assign_sequence_by_route(spaces, route_polyline, start_num, exclude_list):
    """
    依據 route_polyline 計算 spaces 的順序。
    route_polyline 是點陣列 [[x1, y1], [x2, y2], ...]
    排定後賦予 unit_id 並跳過 exclude_list。
    """
    
    # 預處理每段線的累積長度
    seg_lengths = []
    total_len = 0
    for i in range(len(route_polyline)-1):
        d = _distance(route_polyline[i], route_polyline[i+1])
        seg_lengths.append(total_len)
        total_len += d
        
    space_distances = []
    
    for space in spaces:
        cx = (space["min_x"] + space["max_x"]) / 2
        cy = (space["min_y"] + space["max_y"]) / 2
        
        min_dist_to_route = float('inf')
        accumulated_dist_along_route = 0
        
        # 尋找距離此空間中心最近的線段與投影點
        for i in range(len(route_polyline)-1):
            a = route_polyline[i]
            b = route_polyline[i+1]
            closest, t_param = _closest_point_on_segment((cx, cy), a, b)
            
            d_to_route = _distance((cx, cy), closest)
            if d_to_route < min_dist_to_route:
                min_dist_to_route = d_to_route
                # 該點在整條軌跡上的累積長度 = 這條線段起點累計長度 + t * 這條線段長度
                segment_len = _distance(a, b)
                accumulated_dist_along_route = seg_lengths[i] + t_param * segment_len
                
        # 紀錄距離起點的長度作為排序依據
        space_distances.append({
            "space": space,
            "dist_along_route": accumulated_dist_along_route
        })
        
    # 按軌跡長度排序
    space_distances.sort(key=lambda item: item["dist_along_route"])
    
    current_num = start_num
    exclude_set = set(exclude_list)
    results = []
    
    for item in space_distances:
        while current_num in exclude_set:
            current_num += 1
            
        space_assigned = item["space"].copy()
        space_assigned["unit_id"] = str(current_num)
        results.append(space_assigned)
        current_num += 1
        
    return results
