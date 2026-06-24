"""
com_retry.py
COM RPC_E_CALL_REJECTED 防禦層

將 AutoCAD COM 的「忙碌拒絕」錯誤 (-2147418111) 封裝成可靠的重試機制，
讓上層呼叫者不必關心底層的 COM 狀態管理。

核心策略：
- 指數退避 (Exponential Backoff) 避免對忙碌的 COM Server 連續轟炸
- 僅針對 RPC_E_CALL_REJECTED 重試，其他錯誤直接穿透
- extract_entities_safe 提供完整的實體提取流程，內建對每個 COM 操作的防護
"""
import time
import logging

logger = logging.getLogger(__name__)

# Windows COM 「接收者已拒絕這個呼叫」的標準 HRESULT
RPC_E_CALL_REJECTED = -2147418111


def _is_rpc_rejected(exc: Exception) -> bool:
    """判斷此例外是否為 RPC_E_CALL_REJECTED"""
    hresult = getattr(exc, "hresult", None)
    if hresult is not None:
        return hresult == RPC_E_CALL_REJECTED

    # NOTE: pywintypes.com_error 有時把 hresult 放在 args[0]
    if hasattr(exc, "args") and exc.args and isinstance(exc.args[0], int):
        return exc.args[0] == RPC_E_CALL_REJECTED

    return False


def com_call_with_retry(fn, max_retries=10, base_delay=1.0,
                        args=None, kwargs=None):
    """
    呼叫 COM 函式 fn(*args, **kwargs)，遇到 RPC_E_CALL_REJECTED 時自動重試。

    使用指數退避: delay = base_delay * 2^attempt
    非 RPC 拒絕的錯誤會直接穿透（不重試）。
    """
    args = args or ()
    kwargs = kwargs or {}
    last_exc = None

    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if not _is_rpc_rejected(e):
                # 非 RPC 拒絕 → 直接穿透
                raise
            last_exc = e
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "COM RPC_E_CALL_REJECTED (attempt %d/%d), 等待 %.1fs 後重試...",
                attempt + 1, max_retries, delay,
            )
            time.sleep(delay)

    # 所有重試耗盡，拋出最後一次的 COM 例外
    raise last_exc


def com_getattr_safe(obj, attr_name, default=None, max_retries=10,
                     base_delay=1.0):
    """
    安全地存取 COM 物件的屬性，遇到 RPC 拒絕時自動重試。
    超過重試次數後回傳 default（而非拋例外），適合用於非關鍵屬性。
    """
    for attempt in range(max_retries):
        try:
            return getattr(obj, attr_name)
        except Exception as e:
            if not _is_rpc_rejected(e):
                # 非 RPC 拒絕 → 回傳預設值
                return default
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "COM 屬性 '%s' 存取被拒 (attempt %d/%d), 等待 %.1fs",
                attr_name, attempt + 1, max_retries, delay,
            )
            time.sleep(delay)

    # 耗盡重試 → 回傳預設值
    return default


def _extract_layer_colors(doc, max_retries=5, base_delay=0.5):
    """安全地提取圖層顏色映射表"""
    layer_colors = {}
    for attempt in range(max_retries):
        try:
            for lyr in doc.Layers:
                name = getattr(lyr, "Name", "")
                color = getattr(lyr, "color", 256)
                layer_colors[name] = color
            return layer_colors
        except Exception as e:
            if not _is_rpc_rejected(e):
                return layer_colors
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)
    return layer_colors


def extract_entities_safe(doc, max_retries=10, base_delay=1.0):
    """
    從 AutoCAD Document 安全地提取所有實體。

    每個 COM 呼叫都有獨立的重試保護：
    - doc.Layers 迭代
    - model.Count
    - model.Item(i)
    - entity 屬性存取 (ObjectName, Color, Layer, etc.)

    單一實體提取失敗不會中斷整個流程（安全跳過）。
    model.Count 永久失敗則向上拋出例外。
    """
    # 1. 圖層顏色
    layer_colors = _extract_layer_colors(doc, max_retries=max_retries,
                                         base_delay=base_delay)

    # 2. 取得 ModelSpace 物件
    model = doc.ModelSpace

    # 3. model.Count — 關鍵操作，失敗則向上拋出
    model_count = com_call_with_retry(
        lambda: model.Count,
        max_retries=max_retries,
        base_delay=base_delay,
    )

    # 4. 迭代每個實體
    entities = []
    allowed_types = frozenset([
        "AcDbText", "AcDbMText", "AcDbBlockReference",
        "AcDbLine", "AcDbPolyline",
    ])


    for i in range(model_count):
        # 4a. 取得實體物件
        entity = None
        for attempt in range(max_retries):
            try:
                raw_entity = model.Item(i)
                import win32com.client.dynamic
                entity = win32com.client.dynamic.Dispatch(raw_entity)
                break
            except Exception as e:
                if not _is_rpc_rejected(e):
                    break  # 非 RPC 拒絕 → 放棄此實體
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)

        if entity is None:
            continue

        # 4b. 讀取實體屬性（安全存取）
        try:
            ent_type = com_getattr_safe(entity, "ObjectName",
                                        max_retries=max_retries,
                                        base_delay=base_delay)
            if ent_type not in allowed_types and "Dimension" not in ent_type:
                continue

            color = com_getattr_safe(entity, "Color", default=256,
                                     max_retries=max_retries,
                                     base_delay=base_delay)
            layer = com_getattr_safe(entity, "Layer", default="",
                                     max_retries=max_retries,
                                     base_delay=base_delay)

            ent_data = {
                "type": ent_type,
                "layer": layer,
                "color": color,
                "effective_color": (layer_colors.get(layer, 256)
                                    if color == 256 else color),
            }

            if "Dimension" in ent_type:
                text_str = com_getattr_safe(entity, "TextString", default="",
                                            max_retries=max_retries,
                                            base_delay=base_delay)
                if not text_str or text_str == '<>':
                    measurement = com_getattr_safe(entity, "Measurement", default=0,
                                                   max_retries=max_retries,
                                                   base_delay=base_delay)
                    text_str = str(round(measurement, 1))
                
                insertion = com_getattr_safe(entity, "TextPosition",
                                             default=(0, 0, 0),
                                             max_retries=max_retries,
                                             base_delay=base_delay)
                ent_data["text"] = text_str
                ent_data["x"] = insertion[0]
                ent_data["y"] = insertion[1]
                ent_data["type"] = "AcDbText"  # 偽裝成 AcDbText
                ent_data["source_type"] = ent_type

            elif ent_type in ("AcDbText", "AcDbMText"):
                text_str = com_getattr_safe(entity, "TextString", default="",
                                            max_retries=max_retries,
                                            base_delay=base_delay)
                insertion = com_getattr_safe(entity, "InsertionPoint",
                                             default=(0, 0, 0),
                                             max_retries=max_retries,
                                             base_delay=base_delay)
                ent_data["text"] = text_str
                ent_data["x"] = insertion[0]
                ent_data["y"] = insertion[1]

            elif ent_type == "AcDbLine":
                start_pt = com_getattr_safe(entity, "StartPoint",
                                            default=(0, 0, 0),
                                            max_retries=max_retries,
                                            base_delay=base_delay)
                end_pt = com_getattr_safe(entity, "EndPoint",
                                          default=(0, 0, 0),
                                          max_retries=max_retries,
                                          base_delay=base_delay)
                ent_data["start_x"] = start_pt[0]
                ent_data["start_y"] = start_pt[1]
                ent_data["end_x"] = end_pt[0]
                ent_data["end_y"] = end_pt[1]
                ent_data["start"] = [start_pt[0], start_pt[1]]
                ent_data["end"] = [end_pt[0], end_pt[1]]

            elif ent_type == "AcDbBlockReference":
                insertion = com_getattr_safe(entity, "InsertionPoint",
                                             default=(0, 0, 0),
                                             max_retries=max_retries,
                                             base_delay=base_delay)
                ent_data["x"] = insertion[0]
                ent_data["y"] = insertion[1]

            elif ent_type == "AcDbPolyline":
                try:
                    coords = com_getattr_safe(entity, "Coordinates",
                                              default=None,
                                              max_retries=max_retries,
                                              base_delay=base_delay)
                    if coords is not None:
                        verts = []
                        if len(coords) % 2 == 0:
                            for j in range(0, len(coords), 2):
                                verts.append([coords[j], coords[j + 1]])
                        elif len(coords) % 3 == 0:
                            for j in range(0, len(coords), 3):
                                verts.append([coords[j], coords[j + 1]])
                        ent_data["vertices"] = verts
                except Exception:
                    pass

            entities.append(ent_data)

        except Exception:
            # 單一實體的屬性讀取全失敗 → 安全跳過
            logger.warning("跳過實體 #%d (屬性存取失敗)", i)
            continue

    return entities
