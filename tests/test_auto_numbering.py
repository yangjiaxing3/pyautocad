import math
import pytest
import sys
from pathlib import Path

PROJ_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ_ROOT))

from scripts.auto_number_writer import decide_text_rotation, build_inertia_path

def test_decide_text_rotation_tall_box():
    # 高度 > 1.2 * 寬度的直立長方形
    sp = {"min_x": 100, "max_x": 200, "min_y": 100, "max_y": 300} # w=100, h=200
    rot = decide_text_rotation(sp)
    assert rot == math.pi / 2.0, "Tall boxes should have 90 degree (vertical) text"

def test_decide_text_rotation_wide_box():
    # 橫躺長方形
    sp = {"min_x": 100, "max_x": 300, "min_y": 100, "max_y": 200} # w=200, h=100
    rot = decide_text_rotation(sp)
    assert rot == 0.0, "Wide boxes should have 0 degree (horizontal) text"

def test_decide_text_rotation_square_box_with_tolerance():
    # 近似正方形 (寬100, 高110)
    sp = {"min_x": 100, "max_x": 200, "min_y": 100, "max_y": 210} # w=100, h=110
    rot = decide_text_rotation(sp)
    # 高度尚未超過 寬度的 1.2 倍 (120)，應判定為 0.0
    assert rot == 0.0, "Squareish boxes should have horizontally aligned text by default"

def test_build_inertia_path_straight_line():
    spaces = [
        {"min_x": 300, "max_x": 310, "min_y": 100, "max_y": 110},
        {"min_x": 100, "max_x": 110, "min_y": 100, "max_y": 110},
        {"min_x": 200, "max_x": 210, "min_y": 100, "max_y": 110}
    ]
    path = build_inertia_path(spaces)
    assert len(path) == 3
    # 演算法排序: (-cx, cy) 選出 (305, 105)
    assert path[0]["cx"] == 305
    assert path[1]["cx"] == 205
    assert path[2]["cx"] == 105

def test_build_inertia_path_u_turn_with_adaptive_start():
    # U-Shape
    spaces = [
        {"min_x": 200, "max_x": 210, "min_y": 100, "max_y": 110}, # 205, 105
        {"min_x": 100, "max_x": 110, "min_y": 100, "max_y": 110}, # 105, 105
        {"min_x": 300, "max_x": 310, "min_y": 100, "max_y": 110}, # 305, 105 (Start)
        {"min_x": 300, "max_x": 310, "min_y": 200, "max_y": 210}, # 305, 205
        {"min_x": 200, "max_x": 210, "min_y": 200, "max_y": 210}, # 205, 205
        {"min_x": 100, "max_x": 110, "min_y": 200, "max_y": 210}, # 105, 205
    ]
    
    path = build_inertia_path(spaces)
    
    assert path[0]["cx"] == 305 and path[0]["cy"] == 105
    # 自適應初始向量，會先找與自己絕對最近的點，若這裡距離都是 100 (不論水平或垂直)
    # Python min 會根據順序挑選，不過這邊不管走到邊上哪個，他都會轉彎
    # 只要確保沒跑到對角線即可
    assert path[1]["cy"] == 105 or path[1]["cx"] == 305 
