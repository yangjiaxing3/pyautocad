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

# NOTE: 顏色對照表 — 依據 CAD 圖層顏色判定倉位類型與高度
COLOR_MAPPING: dict[int, tuple[str, float]] = {
    3: ("單", 2.3),    # Green
    8: ("單", 2.0),    # Gray
    251: ("單", 2.0),  # Gray
    6: ("半", 2.8),    # Purple/Magenta
    5: ("雙", 3.2),    # Dark blue
    4: ("雙", 3.3),    # Cyan
    2: ("雙", 3.4),    # Yellow
    30: ("雙", 3.6),   # Orange
    7: ("雙", 4.0),    # White
    0: ("雙", 4.0),    # White/ByBlock
    256: ("雙", 4.0),  # White/ByLayer
}


def _format_unit_id(text: str, prefix: str = "") -> str:
    """將數字部分補零為 3 位，並加上前綴"""
    def pad_num(match: re.Match) -> str:
        return match.group(1).zfill(3)

    padded = re.sub(r"(\d+)", pad_num, text)
    return f"{prefix}{padded}" if prefix else padded


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

        if re.match(r"^\d+(\.\d+)?$", txt):
            dims.append(t)
        elif "單" in txt or "雙" in txt or "半" in txt:
            attrs.append(t)
        elif re.match(r"^[A-Za-z]+.*?\d+", txt) or re.match(r"^\d+$", txt):
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

    # 6. 使用文字座標+顏色進行精準比對（直接從文字座標匹配）
    results = []
    for b in boxes:
        bx, by = b.get("x", 0), b.get("y", 0)

        # 找最近的屬性標籤
        closest_attr = None
        min_dist = float("inf")
        for a in attrs:
            dist = math.hypot(a.get("x", 0) - bx, a.get("y", 0) - by)
            if dist < min_dist:
                min_dist = dist
                closest_attr = a

        # 找最近的兩個尺寸
        sorted_dims = sorted(
            dims, key=lambda d: math.hypot(d.get("x", 0) - bx, d.get("y", 0) - by)
        )
        nearest_dims = sorted_dims[:2]

        # 判定 W 和 D
        w_val = None
        d_val = None
        for d in nearest_dims:
            if math.hypot(d.get("x", 0) - bx, d.get("y", 0) - by) > dim_distance_threshold:
                continue
            val = round(float(d["text"]) / 1000.0, 2)
            if d.get("color") == 2:  # Yellow → Width
                w_val = val
            else:
                d_val = val

        if w_val is None and len(nearest_dims) >= 1:
            w_val = round(float(nearest_dims[0]["text"]) / 1000.0, 2)
        if d_val is None and len(nearest_dims) >= 2:
            d_val = round(float(nearest_dims[1]["text"]) / 1000.0, 2)

        # 判定 Type 與 H
        attr_type = ""
        h_val: float | str = ""

        if closest_attr and min_dist < 500:
            c = closest_attr.get("color", -1)
            if c in COLOR_MAPPING:
                attr_type, h_val = COLOR_MAPPING[c]
            else:
                attr_type, h_val = "單", 2.3

        if not attr_type:
            c = b.get("color", -1)
            if c in COLOR_MAPPING:
                attr_type, h_val = COLOR_MAPPING[c]

        if w_val is not None and d_val is not None:
            results.append({
                "倉位號碼": _format_unit_id(b["text"], prefix),
                "屬性": attr_type,
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
