"""
main_pipeline.py
倉位解析核心 Pipeline — 從 CAD JSON 到結構化結果

設計為 pure function，方便被 Streamlit UI / FastAPI Server / CLI 等多種介面呼叫。
"""
import json
import re
import math
import logging
from typing import Any
from io import BytesIO

import pandas as pd

from cad_processor import (
    filter_excluded_texts,
    extract_lines_and_texts,
    group_lines_to_polygons,
    identify_pillars,
    merge_adjacent_spaces,
    bind_texts_to_spaces,
    calculate_net_dimensions,
    assign_sequence_by_route,
    assign_orientations_by_magenta,
)

logger = logging.getLogger(__name__)

# NOTE: 顏色對照表 — 依據 CAD 圖層顏色判定倉位類型與高度 (單位改為 mm)
COLOR_MAPPING: dict[int, tuple[str, float]] = {
    3: ("單", 2300),    # Green
    8: ("單", 2000),    # Gray
    251: ("單", 2000),  # Gray
    6: ("半", 2800),    # Purple/Magenta
    5: ("雙", 3200),    # Dark blue
    4: ("雙", 3300),    # Cyan
    2: ("雙", 3400),    # Yellow
    30: ("雙", 3600),   # Orange
    7: ("雙", 4000),    # White
    0: ("雙", 4000),    # White/ByBlock
    256: ("雙", 4000),  # White/ByLayer
}


def _format_unit_id(text: str, prefix: str = "") -> str:
    """提取裡面唯一的數字，並補足3位附上乾淨的 Prefix，避免出現 HDHD 的錯誤"""
    match = re.search(r"(\d+)", text)
    if match:
        num = match.group(1).zfill(3)
        return f"{prefix}{num}" if prefix else num
    return text


def _categorize_texts(texts: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """
    將文字分為三類：
    - boxes: 倉位號碼 (e.g. WU 112, HD102, 或純數字編號)
    - dims: 尺寸數值 (e.g. 1200, 2.5)
    - attrs: 屬性文字 (含「單/雙/半」)
    """
    boxes = []
    dims = []
    attrs = []

    for t in texts:
        txt = t.get("text", "").strip()
        if not txt:
            continue

        is_pure_number = re.match(r"^\d+(\.\d+)?$", txt)
        has_prefix = re.match(r"^[A-Za-z]+.*?\d+", txt)

        if "單" in txt or "雙" in txt or "半" in txt:
            attrs.append(t)
        elif has_prefix:
            if len(txt) <= 12:
                boxes.append(t)
        elif is_pure_number:
            num = float(txt)
            c = t.get("color", -1)
            # 如果顏色明確為 2 或 6，必定為尺寸
            if c in (2, 6):
                dims.append(t)
            # 若不是特定色，但數值代表合理的尺寸 (>= 500mm)，也歸為尺寸
            elif num >= 500:
                dims.append(t)
            # 其餘較小的純數字(例如 "1", "12", "104")，視為倉位編號
            else:
                if len(txt) <= 8:
                    boxes.append(t)

    return boxes, dims, attrs


def run_pipeline(
    cad_data: list[dict[str, Any]],
    prefix: str = "",
    start_num: int = 1,
    exclude_list: list[str] | None = None,
    route_polyline: list[list[float]] | None = None,
    line_stitch_threshold: float = 10.0,
    max_pillar_size: float = 800.0,
    dim_distance_threshold: float = 800.0,
) -> list[dict[str, Any]]:
    """
    倉位解析核心 Pipeline。

    Args:
        cad_data: 從 AutoCAD 匯出的 entity 列表
        prefix: 倉位號碼前綴 (e.g. "HD")
        start_num: 起始編號
        exclude_list: 排除的號碼字串列表 (e.g. ["004", "013"])
        route_polyline: 軌跡引導線座標 (用於排序)
        line_stitch_threshold: 散線縫合閾值 (mm)
        max_pillar_size: 柱子最大尺寸 (mm)
        dim_distance_threshold: 尺寸文字與倉位的最大關聯距離 (mm)

    Returns:
        結構化結果列表: [{ unit_id, type, W, D, H }, ...]
    """
    if exclude_list is None:
        exclude_list = []

    # NOTE: 防禦性拆包 — 呼叫者可能傳入 {"entities": [...]} 格式的 dict
    if isinstance(cad_data, dict) and "entities" in cad_data:
        cad_data = cad_data["entities"]

    logger.info("Pipeline 啟動：%d 個 entities, prefix=%s", len(cad_data), prefix)

    if not route_polyline:
        for ent in cad_data:
            if ent.get("type") == "AcDbPolyline" and "ROUTE" in str(ent.get("layer", "")).upper():
                route_polyline = ent.get("vertices")
                logger.info("Found auto-routing polyline path!")
                break

    # 1. 過濾排除項目
    clean_data = filter_excluded_texts(cad_data, exclude_list)

    # 2. 分離線段與文字
    lines, all_texts, arrow_lines = extract_lines_and_texts(clean_data)
    logger.info("提取出 %d 條線段, %d 個文字標籤, %d 個合併箭頭", len(lines), len(all_texts), len(arrow_lines))

    # 3. 文字分類
    boxes, dims, attrs = _categorize_texts(all_texts)
    logger.info("分類結果：%d 倉位號碼, %d 尺寸值, %d 屬性標籤", len(boxes), len(dims), len(attrs))

    # 4. 散線縫合 → 生成多邊形 Bounding Box
    polygons = group_lines_to_polygons(lines, threshold=line_stitch_threshold)
    logger.info("辨識出 %d 個封閉空間 (含柱子)", len(polygons))

    # 5. 分離柱子與正常空間
    pillars, spaces = identify_pillars(polygons, max_pillar_size=max_pillar_size)
    logger.info("物理辨識 柱子: %d, 可用空間: %d", len(pillars), len(spaces))

    # 5.5 依據紅色箭頭進行倉位合併
    spaces = merge_adjacent_spaces(spaces, arrow_lines)
    logger.info("合併後可用空間: %d", len(spaces))

    # 5.6 利用桃紅色三角形判斷倉位朝向 (orient)
    spaces = assign_orientations_by_magenta(spaces, cad_data)
    logger.info("已完成倉位朝向解析 (orient)")

    # 如果物理空間數量遠小於屬性標籤數量，說明線段縫合失敗 (例如網格交叉而非獨立矩形)
    # 改以「屬性標籤」作為倉位的虛擬空間節點 (Virtual Spaces)
    if len(spaces) < len(attrs) * 0.5 and len(attrs) > 0:
        logger.info("物理空間數量異常，啟動虛擬錨點模式 (以屬性標籤為倉位中心)")
        virtual_spaces = []
        for a in attrs:
            x, y = a.get("x", 0), a.get("y", 0)
            virtual_spaces.append({
                "min_x": x - 100, "max_x": x + 100,
                "min_y": y - 100, "max_y": y + 100,
                "color": a.get("color", 256)
            })
        spaces = virtual_spaces
        logger.info("虛擬空間節點數量: %d", len(spaces))

    from cad_processor import SpatialHashGrid
    # 預建空間雜湊網格 (Spatial Hash Grids) 降低 O(N²) 的效能死角
    dim_grid = SpatialHashGrid(cell_size=dim_distance_threshold)
    for i, d in enumerate(dims):
        dim_grid.insert(d.get("x", 0), d.get("y", 0), i)

    attr_grid = SpatialHashGrid(cell_size=800.0)
    for i, a in enumerate(attrs):
        attr_grid.insert(a.get("x", 0), a.get("y", 0), i)

    results = []

    # 決定每個 Polyline (space) 的命名
    sequenced_spaces = []

    if (route_polyline or len(boxes) < len(spaces) * 0.1) and spaces:
        if route_polyline:
            logger.info("採用 軌跡動線模式 (Polyline Routing)")
            from cad_processor import assign_sequence_by_route
            sequenced_spaces = assign_sequence_by_route(spaces, route_polyline, start_num, exclude_list)
        else:
            logger.info("採用 自動蛇行路由模式 (Auto-Snake Routing) 因為缺乏足夠的倉位編號標籤")
            from cad_route_logic import build_visual_aisle_path
            path_tuples = build_visual_aisle_path(spaces)
            curr_num = start_num
            for cx, cy, sp in path_tuples:
                while str(curr_num).zfill(3) in exclude_list or str(curr_num) in exclude_list:
                    curr_num += 1
                sp["unit_id"] = curr_num
                sequenced_spaces.append(sp)
                curr_num += 1
    else:
        logger.info("採用 Polyline 綁定命名模式 (Polyline Binding)")
        bindings = bind_texts_to_spaces(boxes, spaces)
        for i, sp in enumerate(spaces):
            bound_texts = bindings.get(i, [])
            if bound_texts:
                # 找出最靠近 polyline 中心的文字
                cx = (sp["min_x"] + sp["max_x"]) / 2
                cy = (sp["min_y"] + sp["max_y"]) / 2
                best_text = min(bound_texts, key=lambda b: math.hypot(b.get("x", 0) - cx, b.get("y", 0) - cy))
                txt = best_text.get("text", "")
                
                sp["unit_id_str"] = _format_unit_id(txt, prefix)
                sequenced_spaces.append(sp)

    # 統一處理 sequenced_spaces 撈取 W/D
    for s in sequenced_spaces:
        bx = (s["min_x"] + s["max_x"]) / 2
        by = (s["min_y"] + s["max_y"]) / 2
        
        if "unit_id_str" in s:
            unit_id = s["unit_id_str"]
            if not unit_id:
                continue
        else:
            raw_id = str(s["unit_id"])
            unit_id = f"{prefix}{raw_id.zfill(3)}" if prefix else raw_id.zfill(3)

        # 從空間雜湊網格中尋找鄰近屬性標籤
        closest_attr = None
        min_dist = float("inf")
        candidate_attr_indices = attr_grid.query_radius(bx, by, 800.0)
        for idx in candidate_attr_indices:
            a = attrs[idx]
            dist = math.hypot(a.get("x", 0) - bx, a.get("y", 0) - by)
            if dist < min_dist:
                min_dist = dist
                closest_attr = a

        # 找附近的尺寸標註
        search_radius = dim_distance_threshold * 2 if s.get("is_merged") else dim_distance_threshold
        candidate_dim_indices = dim_grid.query_radius(bx, by, search_radius)
        candidate_dims = [dims[idx] for idx in candidate_dim_indices]
        candidate_dims = [
            d for d in candidate_dims
            if math.hypot(d.get("x", 0) - bx, d.get("y", 0) - by) <= search_radius
        ]

        # 判定 W 和 D
        w_val = None
        d_val = None
        orient = s.get("orient", "H")
        is_merged = s.get("is_merged", False)

        if candidate_dims:
            x_vals = []
            y_vals = []
            for d in candidate_dims:
                val = round(float(d["text"]))
                dx = d.get("x", bx)
                dy = d.get("y", by)
                
                if abs(dy - by) > abs(dx - bx):
                    x_vals.append(val)
                else:
                    y_vals.append(val)
            
            if orient == "H":
                w_cands = x_vals
                d_cands = y_vals
            else:
                w_cands = y_vals
                d_cands = x_vals

            if is_merged:
                if d_cands:
                    d_val = sum(d_cands)
                else:
                    d_val = sum([round(float(d["text"])) for d in candidate_dims])
                    
                if w_cands:
                    w_val = max(set(w_cands), key=w_cands.count)
                else:
                    w_val = d_val
            else:
                w_val = w_cands[0] if w_cands else None
                d_val = d_cands[0] if d_cands else None
                
                if w_val is None and d_val is not None:
                    w_val = d_val
                elif d_val is None and w_val is not None:
                    d_val = w_val
                elif w_val is None and d_val is None:
                    vals = sorted(set(round(float(d["text"])) for d in candidate_dims))
                    w_val, d_val = (vals[0], vals[1] if len(vals) > 1 else vals[0])

        # 判定 Type 與 H
        attr_type = ""
        h_val = 0.0

        if closest_attr and min_dist < 800:
            c = closest_attr.get("color", -1)
            if c in COLOR_MAPPING:
                attr_type, h_val = COLOR_MAPPING[c]
            else:
                attr_type, h_val = "單", 2300

        if not attr_type:
            c = s.get("color", -1)
            if c in COLOR_MAPPING:
                attr_type, h_val = COLOR_MAPPING[c]

        results.append({
            "倉位號碼": unit_id,
            "屬性": attr_type or "單",
            "W": w_val,
            "D": d_val,
            "H": h_val,
            "cx": bx,
            "cy": by,
        })

    # 7. 排序
    results.sort(key=lambda x: x["倉位號碼"])

    # 8. 去重
    seen = set()
    unique_results = []
    for r in results:
        key = (r["倉位號碼"], r["W"], r["D"])
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    logger.info("Pipeline 完成：產出 %d 筆倉位資料", len(unique_results))
    return unique_results


def results_to_dataframe(results: list[dict[str, Any]]) -> pd.DataFrame:
    """將 pipeline 結果轉為 DataFrame"""
    return pd.DataFrame(results)


def results_to_excel_bytes(results: list[dict[str, Any]]) -> bytes:
    """將結果轉為 Excel 二進位內容（可直接寫入檔案或 HTTP 回應）"""
    df = results_to_dataframe(results)
    buffer = BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


# CLI 入口 — 維持向後相容
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    try:
        raw_data = json.load(open("cad_dump.json", encoding="utf-8"))
        data = raw_data.get("entities", raw_data) if isinstance(raw_data, dict) else raw_data
    except FileNotFoundError:
        logger.error("未找到 cad_dump.json。請先使用提取腳本從 CAD 匯出資料。")
        raise SystemExit(1)

    exclude = ["004", "013", "044", "444", "4444"]
    results = run_pipeline(data, prefix="TD", start_num=500, exclude_list=exclude)

    if results:
        import os
        output_path = os.path.abspath(r"ref\Pipeline_抽出結果.xlsx")
        excel_bytes = results_to_excel_bytes(results)
        with open(output_path, "wb") as f:
            f.write(excel_bytes)
        logger.info("Excel 已產出: %s", output_path)
    else:
        logger.warning("未產出任何結果。")
