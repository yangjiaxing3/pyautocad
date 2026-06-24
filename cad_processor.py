import math
import logging

logger = logging.getLogger(__name__)

# Color mapping for height detection
HEIGHT_COLOR_MAP = {
    3: 2300,   # 單 綠
    8: 2000,   # 雙 灰
    6: 2800,   # 半 紫(洋紅)
    5: 3200,   # 雙 深藍
    4: 3300,   # 雙 水藍
    2: 3400,   # 雙 黃
    30: 3600,  # 雙 橘 (Assuming 30-40 range, exact relies on ACI 30)
    7: 4000    # 雙 白 (7 is white/black)
}

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
    """
    分離線段與文字，並同時抓出代表「箭頭合併」的洋紅或紅色線段
    """
    lines = []
    texts = []
    arrow_lines = []
    
    for ent in entities:
        if ent.get("type") in ["AcDbText", "AcDbMText"]:
            texts.append(ent)
        elif ent.get("type") == "AcDbLine":
            lines.append(ent)
            
            # Detect merge arrow (color 1 Red, color 6 Magenta)
            eff_color = ent.get("effective_color", ent.get("color", 256))
            if eff_color in (1, 6):
                arrow_lines.append(ent)
                
        elif ent.get("type") == "AcDbBlockReference":
            eff_color = ent.get("effective_color", ent.get("color", 256))
            if eff_color in (1, 6) and "x" in ent and "y" in ent:
                arrow_lines.append({
                    "start": [ent["x"], ent["y"]],
                    "end": [ent["x"], ent["y"]],
                    "type": "marker"
                })
                
        elif ent.get("type") == "AcDbPolyline":
            # 排除 ROUTE 線，因為那是引導線
            if "ROUTE" in str(ent.get("layer", "")).upper():
                continue
            vertices = ent.get("vertices", [])
            # 將 polyline 的頂點轉換為線段
            for i in range(len(vertices) - 1):
                poly_line = {
                    "type": "AcDbLine",
                    "layer": ent.get("layer"),
                    "color": ent.get("color"),
                    "effective_color": ent.get("effective_color"),
                    "start": vertices[i],
                    "end": vertices[i+1],
                    "start_x": vertices[i][0],
                    "start_y": vertices[i][1],
                    "end_x": vertices[i+1][0],
                    "end_y": vertices[i+1][1],
                }
                lines.append(poly_line)
                
                # Check for arrow line in polyline segments
                eff_color = ent.get("effective_color", ent.get("color", 256))
                if eff_color in (1, 6):
                    arrow_lines.append(poly_line)
                
    return lines, texts, arrow_lines

def _distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

class SpatialHashGrid:
    """O(1) 查表的空間雜湊分區系統"""
    def __init__(self, cell_size: float):
        self.cell_size = cell_size
        self.cells = {}

    def _get_key(self, x: float, y: float) -> tuple[int, int]:
        return (int(x // self.cell_size), int(y // self.cell_size))

    def insert(self, x: float, y: float, item: any):
        key = self._get_key(x, y)
        if key not in self.cells:
            self.cells[key] = []
        self.cells[key].append(item)

    def query_radius(self, x: float, y: float, radius: float) -> set:
        candidates = set()
        min_key = self._get_key(x - radius, y - radius)
        max_key = self._get_key(x + radius, y + radius)
        
        for cx in range(min_key[0], max_key[0] + 1):
            for cy in range(min_key[1], max_key[1] + 1):
                if (cx, cy) in self.cells:
                    candidates.update(self.cells[(cx, cy)])
        return candidates

def group_lines_to_polygons(lines, threshold=5.0):
    """Line Stitching 演算法，找出連通區域並產出 Bounding Box"""
    n = len(lines)
    parent = list(range(n))
    rank = [0] * n

    # NOTE: 迭代式二段路徑壓縮 — 避免遞迴版本在大量線段時觸發
    # RecursionError (Python 預設遞迴深度 ~1000，而 CAD 圖面線段數可達數萬)
    def find(i):
        root = i
        while parent[root] != root:
            root = parent[root]
        # 第二輪：沿路壓縮，所有節點直接指向根
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    # NOTE: 按秩合併 (Union by Rank) — 將矮樹掛到高樹下，
    # 保證樹高 ≤ O(log n)，進一步降低 find 遍歷深度
    def union(i, j):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            if rank[root_i] < rank[root_j]:
                parent[root_i] = root_j
            elif rank[root_i] > rank[root_j]:
                parent[root_j] = root_i
            else:
                parent[root_j] = root_i
                rank[root_i] += 1
            
    # 使用空間分區加速 O(N^2) -> O(N)
    grid = SpatialHashGrid(cell_size=threshold)
    for i, line in enumerate(lines):
        grid.insert(line['start'][0], line['start'][1], i)
        grid.insert(line['end'][0], line['end'][1], i)

    for i in range(n):
        si = lines[i]['start']
        ei = lines[i]['end']
        
        # 尋找鄰居
        candidates = set()
        candidates.update(grid.query_radius(si[0], si[1], threshold))
        candidates.update(grid.query_radius(ei[0], ei[1], threshold))
        
        for j in candidates:
            if i >= j: continue  # 避免重複計算或自己算自己
            
            sj = lines[j]['start']
            ej = lines[j]['end']
            
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
        colors = []
        for line in comp:
            xs.extend([line['start'][0], line['end'][0]])
            ys.extend([line['start'][1], line['end'][1]])
            if "color" in line:
                colors.append(line["color"])
                
        dominant_color = max(set(colors), key=colors.count) if colors else -1

        if xs and ys:
            polygons.append({
                "min_x": min(xs),
                "max_x": max(xs),
                "min_y": min(ys),
                "max_y": max(ys),
                "color": dominant_color
            })
    return polygons

def identify_pillars(polygons, max_pillar_size=800):
    """過濾出尺寸小於 max_pillar_size 的多邊形作為柱子，並過濾單線條雜訊"""
    pillars = []
    spaces = []
    for poly in polygons:
        w = poly["max_x"] - poly["min_x"]
        h = poly["max_y"] - poly["min_y"]
        
        # NOTE: 過濾無效空間 (0x1060 的單一線段、破洞未閉合的線)
        # 由於我們即將取消 color==251 過濾，這能精確防止輔助線變成幻影倉位
        if w < 200 or h < 200:
            continue
            
        if w <= max_pillar_size and h <= max_pillar_size:
            pillars.append(poly)
        else:
            spaces.append(poly)
    return pillars, spaces

def check_arrow_intersection(arrow_lines, sp):
    """檢查是否有任何箭頭線段與該 Space Bounding Box 相交或包接"""
    for arr in arrow_lines:
        sx, sy = arr['start'][0], arr['start'][1]
        ex, ey = arr['end'][0], arr['end'][1]
        
        # Point in box check with tolerance
        tol = 50.0
        s_in = (sp['min_x']-tol <= sx <= sp['max_x']+tol) and (sp['min_y']-tol <= sy <= sp['max_y']+tol)
        e_in = (sp['min_x']-tol <= ex <= sp['max_x']+tol) and (sp['min_y']-tol <= ey <= sp['max_y']+tol)
        
        if s_in or e_in:
            return True, arr # Returns the arrow line
    return False, None

def merge_adjacent_spaces(spaces, arrow_lines):
    """
    依據紅/洋紅箭頭進行倉位合併:
    過濾掉過長的線段(非箭頭)，找出箭頭線段觸碰到的相鄰倉位，建立連通圖並合併。
    """
    if not arrow_lines or len(spaces) < 2:
        return spaces
        
    # 1. 萃取有效的短箭頭線段 (長度 < 1000)
    valid_arrows = []
    for arr in arrow_lines:
        if "start" in arr and "end" in arr:
            sx, sy = arr['start'][0], arr['start'][1]
            ex, ey = arr['end'][0], arr['end'][1]
            if math.hypot(ex-sx, ey-sy) < 1000.0:
                valid_arrows.append(arr)
                
    if not valid_arrows:
        return spaces
        
    # 2. 建立連通圖
    parent = {i: i for i in range(len(spaces))}
    def find(i):
        if parent[i] == i: return i
        parent[i] = find(parent[i])
        return parent[i]
    def union(i, j):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    tol = 100.0
    for arr in valid_arrows:
        sx, sy = arr['start'][0], arr['start'][1]
        ex, ey = arr['end'][0], arr['end'][1]
        
        arr_min_x, arr_max_x = min(sx, ex), max(sx, ex)
        arr_min_y, arr_max_y = min(sy, ey), max(sy, ey)
        
        # 找出這條線段觸碰到的所有空間
        touching = []
        for i, sp in enumerate(spaces):
            if (arr_min_x - tol <= sp['max_x'] and arr_max_x + tol >= sp['min_x'] and
                arr_min_y - tol <= sp['max_y'] and arr_max_y + tol >= sp['min_y']):
                touching.append(i)
                
        # 將觸碰到的空間互相連結
        if len(touching) >= 2:
            first = touching[0]
            for other in touching[1:]:
                union(first, other)
                
    # 3. 收集連通群組並合併
    groups = {}
    for i in range(len(spaces)):
        root = find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(i)
        
    merged_spaces = []
    merge_count = 0
    
    for root, indices in groups.items():
        if len(indices) == 1:
            merged_spaces.append(spaces[indices[0]])
        else:
            merge_count += len(indices) - 1
            min_x = min(spaces[idx]['min_x'] for idx in indices)
            max_x = max(spaces[idx]['max_x'] for idx in indices)
            min_y = min(spaces[idx]['min_y'] for idx in indices)
            max_y = max(spaces[idx]['max_y'] for idx in indices)
            
            new_space = {
                "min_x": min_x, "max_x": max_x,
                "min_y": min_y, "max_y": max_y,
                "color": spaces[indices[0]].get('color', -1),
                "is_merged": True,
                "merged_from_count": len(indices),
            }
            # 判斷合併方向：比較 X 跨度增量 vs Y 跨度增量
            # NOTE: 如果合併後的 X 跨度遠大於單一空間，代表是水平合併 (merge_axis='x')
            single_widths = [spaces[idx]['max_x'] - spaces[idx]['min_x'] for idx in indices]
            single_heights = [spaces[idx]['max_y'] - spaces[idx]['min_y'] for idx in indices]
            merged_w = max_x - min_x
            merged_h = max_y - min_y
            avg_single_w = sum(single_widths) / len(single_widths)
            avg_single_h = sum(single_heights) / len(single_heights)
            if merged_w > avg_single_w * 1.5:
                new_space["merge_axis"] = "x"
            elif merged_h > avg_single_h * 1.5:
                new_space["merge_axis"] = "y"
            else:
                new_space["merge_axis"] = "y"  # 預設上下合併
            for key in ['orient', 'air_wall']:
                for idx in indices:
                    if key in spaces[idx]:
                        new_space[key] = spaces[idx][key]
                        break
            merged_spaces.append(new_space)
            
    if merge_count > 0:
        logger.info(f"經箭頭群集指引，執行了 {merge_count} 次倉位合併！")
    return merged_spaces


def _rect_intersect_area(r1, r2):
    """計算兩個 Bounding Box 的交集面積"""
    dx = min(r1["max_x"], r2["max_x"]) - max(r1["min_x"], r2["min_x"])
    dy = min(r1["max_y"], r2["max_y"]) - max(r1["min_y"], r2["min_y"])
    if dx > 0 and dy > 0:
        return dx * dy
    return 0

def detect_height_by_color(space_polygon, texts):
    """
    透過綁定在該倉位內的文字顏色，決定倉位的高度。
    """
    space_height = None
    
    # Priority words: 單, 雙, 半
    for text in texts:
        content = text.get("text", "")
        # Check if this text is an attribute label, not a dimension
        if any(keyword in content for keyword in ["單", "雙", "半"]):
            # The color is stored in effective_color ideally, or color
            color = text.get("effective_color", text.get("color", 256))
            
            # If color maps exactly:
            if color in HEIGHT_COLOR_MAP:
                space_height = HEIGHT_COLOR_MAP[color]
                break
                
            # Fallback heuristic if it's 3X (Orange range)
            if 30 <= color <= 40:
                space_height = 3600
                break

    # If no mapping found, return a default or None
    return space_height

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
            # Bounding box inclusion check first
            if poly["min_x"] <= tx <= poly["max_x"] and poly["min_y"] <= ty <= poly["max_y"]:
                # Strong binding
                best_idx = i
                break
                
            dist = _distance((tx, ty), (cx, cy))
            if dist < best_dist:
                best_dist = dist
                best_idx = i

        if best_idx >= 0:
            bindings[best_idx].append(text)

    return bindings

def calculate_net_dimensions(space_polygon, pillars_polygons, height=None):
    """扣除跨圖紙讀入的柱子面積，求得淨面積與長寬，並附帶高"""
    w = space_polygon["max_x"] - space_polygon["min_x"]
    d = space_polygon["max_y"] - space_polygon["min_y"]
    gross_area = w * d
    
    pillar_area = 0
    pillar_desc = []
    
    for p in pillars_polygons:
        intersect = _rect_intersect_area(space_polygon, p)
        if intersect > 0:
            pillar_area += intersect
            pw = p["max_x"] - p["min_x"]
            pd = p["max_y"] - p["min_y"]
            ph = height if height else 0  # Assuming pillar goes all the way up
            pillar_desc.append(f"{pw:.0f}x{pd:.0f}x{ph}")
            
    net_area = gross_area - pillar_area
    
    desc = f"{w:.0f}x{d:.0f}x{height if height else '???'}"
    if pillar_desc:
        desc += f" - {' - '.join(pillar_desc)}"
        
    return {
        "width": w,
        "depth": d,
        "height": height,
        "gross_area": gross_area,
        "pillar_area": pillar_area,
        "net_area": net_area,
        "raw_desc": desc
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
        
    # 修正：加入次要排序鍵，確保面對面的對稱倉位能有穩定的先後順序
    # 使用 round(, 1) 消除極微小的浮點公差
    space_distances.sort(key=lambda item: (
        round(item["dist_along_route"], 1),
        round(item["space"]["min_y"], 1),
        round(item["space"]["min_x"], 1)
    ))

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

def assign_orientations_by_magenta(spaces, all_entities):
    """
    掃描所有的實體，找出桃紅色 (Color 6) 的直線 (大門方向三角形)。
    使用 polygon 群組隔開可能的文字與雜訊。
    比對三角形的尖端朝向，定義為 UP/DOWN/LEFT/RIGHT。
    將 UP/DOWN 轉化為 水平排列 (orient='H')
    將 LEFT/RIGHT 轉化為 垂直排列 (orient='V')
    """
    magenta = [e for e in all_entities if e.get('type') == 'AcDbLine' and e.get('effective_color', e.get('color', 256)) == 6]
    
    for sp in spaces:
        tol = 100
        sp_magentas = []
        for m in magenta:
            sx, sy = m['start'][0], m['start'][1]
            ex, ey = m['end'][0], m['end'][1]
            mx, my = (sx+ex)/2, (sy+ey)/2
            if sp['min_x']-tol <= mx <= sp['max_x']+tol and sp['min_y']-tol <= my <= sp['max_y']+tol:
                sp_magentas.append(m)
                
        import math
        # Group magenta lines to avoid mixing triangles with other magenta texts/symbols
        clusters = []
        for m in sp_magentas:
            added = False
            for c in clusters:
                for cm in c:
                    d1 = math.hypot(m['start'][0]-cm['start'][0], m['start'][1]-cm['start'][1])
                    d2 = math.hypot(m['start'][0]-cm['end'][0], m['start'][1]-cm['end'][1])
                    d3 = math.hypot(m['end'][0]-cm['start'][0], m['end'][1]-cm['start'][1])
                    d4 = math.hypot(m['end'][0]-cm['end'][0], m['end'][1]-cm['end'][1])
                    if min(d1, d2, d3, d4) < 10.0:
                        c.append(m)
                        added = True
                        break
                if added: break
            if not added:
                clusters.append([m])
                
        target_lines = None
        for c in clusters:
            pts = []
            for cm in c: pts.extend([cm['start'], cm['end']])
            pw = max(p[0] for p in pts) - min(p[0] for p in pts)
            ph = max(p[1] for p in pts) - min(p[1] for p in pts)
            if pw <= 500 and ph <= 500 and len(c) >= 2:
                target_lines = c
                break
                
        if not target_lines:
            facing = 'UNKNOWN'
        else:
            raw_pts = []
            for m in target_lines: raw_pts.extend([m['start'], m['end']])
            
            # Unique the points to handle both closed triangles and open arrowheads
            unique_pts = []
            for p in raw_pts:
                rp = (round(p[0], 1), round(p[1], 1))
                if rp not in unique_pts:
                    unique_pts.append(rp)
            pts = unique_pts
            
            min_x = min(p[0] for p in pts)
            max_x = max(p[0] for p in pts)
            min_y = min(p[1] for p in pts)
            max_y = max(p[1] for p in pts)
            w = max_x - min_x
            h = max_y - min_y
            
            pts_at_left = sum(1 for p in pts if abs(p[0] - min_x) <= w*0.2)
            pts_at_right = sum(1 for p in pts if abs(p[0] - max_x) <= w*0.2)
            pts_at_top = sum(1 for p in pts if abs(p[1] - max_y) <= h*0.2)
            pts_at_bot = sum(1 for p in pts if abs(p[1] - min_y) <= h*0.2)
            
            diff_x = abs(pts_at_left - pts_at_right)
            diff_y = abs(pts_at_top - pts_at_bot)
            
            if diff_x > diff_y:
                facing = 'RIGHT' if pts_at_right < pts_at_left else 'LEFT'
            elif diff_y > diff_x:
                facing = 'UP' if pts_at_top < pts_at_bot else 'DOWN'
            else:
                facing = 'UNKNOWN'
                
        if facing in ('UP', 'DOWN'):
            orient = 'H'
        elif facing in ('LEFT', 'RIGHT'):
            orient = 'V'
        else:
            # Fallback to default H
            # Most warehousing aisles are horizontal. Guessing based on aspect ratio causes 
            # wide horizontal rows (e.g., 1492x1200) to misidentify as vertical columns.
            orient = 'H'
            
        sp['orient'] = orient
    return spaces

import math

def assign_air_walls(spaces, arrow_lines):
    """
    從箭頭線中過濾出桃紅色(color=6)線段，組成三角形聚落。
    每個三角形代表倉位的正面，並對反面設置空氣牆(air_wall)。
    """
    magenta_lines = [l for l in arrow_lines if l.get("effective_color", l.get("color")) == 6]
    
    grid = {}
    for line in magenta_lines:
        mx, my = (line['start'][0] + line['end'][0])/2, (line['start'][1] + line['end'][1])/2
        cell = (int(mx//500), int(my//500))
        if cell not in grid: grid[cell] = []
        grid[cell].append(line)

    triangles = []
    for cell_lines in grid.values():
        if len(cell_lines) >= 3:
            xs = [l['start'][0] for l in cell_lines] + [l['end'][0] for l in cell_lines]
            ys = [l['start'][1] for l in cell_lines] + [l['end'][1] for l in cell_lines]
            triangles.append({
                "cx": sum(xs)/len(xs),
                "cy": sum(ys)/len(ys)
            })

    print(f"Info: 為 {len(spaces)} 個倉位分配空氣牆，參考 {len(triangles)} 個桃紅色三角形指標...")

    for sp in spaces:
        scx = (sp['min_x'] + sp['max_x'])/2
        scy = (sp['min_y'] + sp['max_y'])/2
        
        # 找最近的三角形
        min_dist = float('inf')
        nearest_tri = None
        for tri in triangles:
            dist = math.hypot(scx - tri['cx'], scy - tri['cy'])
            if dist < min_dist:
                min_dist = dist
                nearest_tri = tri
                
        # 2000 以內視為有效指示
        if nearest_tri and min_dist < 2000:
            dx = nearest_tri['cx'] - scx
            dy = nearest_tri['cy'] - scy
            
            air_wall = None
            if abs(dy) > abs(dx):
                if dy > 0: # Triangle is North -> Front is North -> Wall is South
                    air_wall = "S"
                else:      # Triangle is South -> Front is South -> Wall is North
                    air_wall = "N"
            else:
                if dx > 0: # Triangle is East -> Front is East -> Wall is West
                    air_wall = "W"
                else:      # Triangle is West -> Front is West -> Wall is East
                    air_wall = "E"
                    
            sp["air_wall"] = air_wall
        else:
            # 預設無牆
            sp["air_wall"] = None
            
    return spaces

