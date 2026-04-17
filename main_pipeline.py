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
    bind_texts_to_spaces,
    calculate_net_dimensions,
    assign_sequence_by_route,
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
    lines, all_texts = extract_lines_and_texts(clean_data)
    logger.info("提取出 %d 條線段, %d 個文字標籤", len(lines), len(all_texts))

    # 3. 文字分類
    boxes, dims, attrs = _categorize_texts(all_texts)
    logger.info("分類結果：%d 倉位號碼, %d 尺寸值, %d 屬性標籤", len(boxes), len(dims), len(attrs))

    # 4. 散線縫合 → 生成多邊形 Bounding Box
    polygons = group_lines_to_polygons(lines, threshold=line_stitch_threshold)
    logger.info("辨識出 %d 個封閉空間 (含柱子)", len(polygons))

    # 5. 分離柱子與正常空間
    pillars, spaces = identify_pillars(polygons, max_pillar_size=max_pillar_size)
    logger.info("柱子: %d, 可用空間: %d", len(pillars), len(spaces))

    from cad_processor import SpatialHashGrid
    # 預建空間雜湊網格 (Spatial Hash Grids) 降低 O(N²) 的效能死角
    dim_grid = SpatialHashGrid(cell_size=dim_distance_threshold)
    for i, d in enumerate(dims):
        dim_grid.insert(d.get("x", 0), d.get("y", 0), i)

    attr_grid = SpatialHashGrid(cell_size=800.0)
    for i, a in enumerate(attrs):
        attr_grid.insert(a.get("x", 0), a.get("y", 0), i)

    results = []

    if route_polyline and spaces:
        # 軌跡動線模式 (Polyline Routing)
        from cad_processor import assign_sequence_by_route
        sequenced_spaces = assign_sequence_by_route(spaces, route_polyline, start_num, exclude_list)
        
        for s in sequenced_spaces:
            bx = (s["min_x"] + s["max_x"]) / 2
            by = (s["min_y"] + s["max_y"]) / 2
            
            # 取出分配好的號碼並補零冠前綴
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

            # 找最近的兩個尺寸
            candidate_dim_indices = dim_grid.query_radius(bx, by, dim_distance_threshold)
            candidate_dims = [dims[idx] for idx in candidate_dim_indices]
            sorted_dims = sorted(
                candidate_dims, key=lambda d: math.hypot(d.get("x", 0) - bx, d.get("y", 0) - by)
            )
            nearest_dims = sorted_dims[:2]

            # 判定 W 和 D
            w_val = None
            d_val = None
            for d in nearest_dims:
                if math.hypot(d.get("x", 0) - bx, d.get("y", 0) - by) > dim_distance_threshold:
                    continue
                val = round(float(d["text"])) # 取 mm 整數
                if d.get("color") == 2:  # Yellow → Width
                    w_val = val
                else:
                    d_val = val

            if w_val is None and len(nearest_dims) >= 1:
                w_val = round(float(nearest_dims[0]["text"]))
            if d_val is None and len(nearest_dims) >= 2:
                d_val = round(float(nearest_dims[1]["text"]))

            # 判定 Type 與 H
            attr_type = ""
            h_val = 0.0

            if closest_attr and min_dist < 800: # 提高容錯
                c = closest_attr.get("color", -1)
                if c in COLOR_MAPPING:
                    attr_type, h_val = COLOR_MAPPING[c]
                else:
                    attr_type, h_val = "單", 2300

            if not attr_type:
                c = s.get("color", -1) # 從空間多邊形提取
                if c in COLOR_MAPPING:
                    attr_type, h_val = COLOR_MAPPING[c]

            results.append({
                "倉位號碼": unit_id,
                "屬性": attr_type or "單",
                "W": w_val,
                "D": d_val,
                "H": h_val,
            })

    else:
        # 傳統文字定錨模式 (Text Anchoring)
        for b in boxes:
            bx, by = b.get("x", 0), b.get("y", 0)
    
            # 找最近的屬性標籤
            closest_attr = None
            min_dist = float("inf")
            candidate_attr_indices = attr_grid.query_radius(bx, by, 800.0)
            for idx in candidate_attr_indices:
                a = attrs[idx]
                dist = math.hypot(a.get("x", 0) - bx, a.get("y", 0) - by)
                if dist < min_dist:
                    min_dist = dist
                    closest_attr = a
    
            # 找最近的兩條尺寸標註
            dims_with_dist = []
            candidate_dim_indices = dim_grid.query_radius(bx, by, dim_distance_threshold)
            for idx in candidate_dim_indices:
                d = dims[idx]
                dist = math.hypot(d.get("x", 0) - bx, d.get("y", 0) - by)
                dims_with_dist.append((dist, d))
            
            dims_with_dist.sort(key=lambda x: x[0])
            nearest_dims = [d[1] for d in dims_with_dist[:2]]
    
            # 判定 W 和 D
            w_val = None
            d_val = None
            for d in nearest_dims:
                if math.hypot(d.get("x", 0) - bx, d.get("y", 0) - by) > dim_distance_threshold:
                    continue
                val = round(float(d["text"])) # 取 mm 整數
                if d.get("color") == 2:  # Yellow → Width
                    w_val = val
                else:
                    d_val = val
    
            if w_val is None and len(nearest_dims) >= 1:
                w_val = round(float(nearest_dims[0]["text"]))
            if d_val is None and len(nearest_dims) >= 2:
                d_val = round(float(nearest_dims[1]["text"]))
    
            # 判定 Type 與 H
            attr_type = ""
            h_val = 0.0
    
            if closest_attr and min_dist < 500:
                c = closest_attr.get("color", -1)
                if c in COLOR_MAPPING:
                    attr_type, h_val = COLOR_MAPPING[c]
                else:
                    attr_type, h_val = "單", 2300
    
            if not attr_type:
                c = b.get("color", -1)
                if c in COLOR_MAPPING:
                    attr_type, h_val = COLOR_MAPPING[c]
    
            results.append({
                "倉位號碼": _format_unit_id(b.get("text", ""), prefix),
                "屬性": attr_type or "單",
                "W": w_val,
                "D": d_val,
                "H": h_val,
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
        data = json.load(open("cad_dump.json", encoding="utf-8"))
    except FileNotFoundError:
        logger.error("未找到 cad_dump.json。請先使用提取腳本從 CAD 匯出資料。")
        raise SystemExit(1)

    exclude = ["004", "013", "044", "444", "4444"]
    results = run_pipeline(data, prefix="", exclude_list=exclude)

    if results:
        import os
        output_path = os.path.abspath(r"ref\Pipeline_抽出結果.xlsx")
        excel_bytes = results_to_excel_bytes(results)
        with open(output_path, "wb") as f:
            f.write(excel_bytes)
        logger.info("Excel 已產出: %s", output_path)
    else:
        logger.warning("未產出任何結果。")
