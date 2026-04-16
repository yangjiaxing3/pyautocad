import pytest
from cad_processor import (
    filter_excluded_texts,
    extract_lines_and_texts,
    group_lines_to_polygons,
    identify_pillars,
    bind_texts_to_spaces,
    calculate_net_dimensions
)

def test_filter_excluded_texts():
    entities = [
        {"type": "AcDbText", "text": "001"},
        {"type": "AcDbText", "text": "004"},
        {"type": "AcDbLine", "start": [0,0], "end": [10,10]}
    ]
    exclude_list = ["004", "013"]
    
    result = filter_excluded_texts(entities, exclude_list)
    assert len(result) == 2
    assert not any(ent.get("text") == "004" for ent in result)

def test_extract_lines_and_texts():
    entities = [
        {"type": "AcDbText", "text": "001"},
        {"type": "AcDbLine", "start": [0,0], "end": [10,10]},
        {"type": "AcDbMText", "text": "002"}
    ]
    lines, texts = extract_lines_and_texts(entities)
    assert len(lines) == 1
    assert len(texts) == 2

def test_group_lines_to_polygons():
    lines = [
        {"type": "AcDbLine", "start": [0, 0], "end": [10, 0]},
        {"type": "AcDbLine", "start": [10, 0], "end": [10, 10]},
        {"type": "AcDbLine", "start": [10, 10], "end": [0, 10]},
        {"type": "AcDbLine", "start": [0, 10], "end": [0, 0]}
    ]
    polygons = group_lines_to_polygons(lines)
    assert len(polygons) == 1
    box = polygons[0]
    assert box['min_x'] == 0
    assert box['max_x'] == 10
    assert box['min_y'] == 0
    assert box['max_y'] == 10

def test_identify_pillars():
    polygons = [
        {"min_x": 0, "max_x": 100, "min_y": 0, "max_y": 100},
        {"min_x": 90, "max_x": 100, "min_y": 90, "max_y": 100}
    ]
    pillars, spaces = identify_pillars(polygons, max_pillar_size=30)
    assert len(pillars) == 1
    assert len(spaces) == 1
    assert pillars[0]["max_x"] == 100

def test_calculate_net_dimensions():
    space = {"min_x": 0, "max_x": 100, "min_y": 0, "max_y": 100}
    pillars = [{"min_x": 80, "max_x": 100, "min_y": 80, "max_y": 100}]
    result = calculate_net_dimensions(space, pillars)
    assert result["width"] == 100
    assert result["depth"] == 100
    assert result["gross_area"] == 10000
    assert result["pillar_area"] == 400
    assert result["net_area"] == 9600

from cad_processor import assign_sequence_by_route

def test_assign_sequence_by_route():
    # 建立 3 個連續空間
    spaces = [
        {"min_x": 20, "max_x": 30, "min_y": 0, "max_y": 10}, # 中心: 25, 5
        {"min_x": 0, "max_x": 10, "min_y": 0, "max_y": 10},  # 中心: 5, 5
        {"min_x": 10, "max_x": 20, "min_y": 0, "max_y": 10}  # 中心: 15, 5
    ]
    # 一條引導線，從 x=0 橫向畫到 x=30 ( y=5 )
    route_polyline = [ [0, 5], [30, 5] ]
    
    # 預期順序是: 中心x為 5(第二個), 15(第三個), 25(第一個)
    # 起始號碼為 1, 排除 [2]
    exclude_list = [2]
    start_num = 1
    
    result = assign_sequence_by_route(spaces, route_polyline, start_num, exclude_list)
    
    # 給定的號碼應為 1, 3, 4
    # 注意 result 是按排序後的順序吐出來
    assert result[0]["unit_id"] == "1"
    assert result[1]["unit_id"] == "3"
    assert result[2]["unit_id"] == "4"


def test_bind_texts_to_spaces():
    """驗證文字能精確綁定到距離最近的 Bounding Box"""
    polygons = [
        {"min_x": 0, "max_x": 100, "min_y": 0, "max_y": 100},   # 中心: 50, 50
        {"min_x": 200, "max_x": 300, "min_y": 0, "max_y": 100},  # 中心: 250, 50
    ]
    texts = [
        {"type": "AcDbText", "text": "001", "x": 40, "y": 60},   # 靠近 polygon[0]
        {"type": "AcDbText", "text": "002", "x": 240, "y": 40},  # 靠近 polygon[1]
        {"type": "AcDbText", "text": "單", "x": 60, "y": 80},    # 靠近 polygon[0]
    ]
    bindings = bind_texts_to_spaces(texts, polygons)
    assert len(bindings[0]) == 2  # 001 + 單
    assert len(bindings[1]) == 1  # 002
    assert bindings[0][0]["text"] == "001"
    assert bindings[1][0]["text"] == "002"
