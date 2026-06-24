# SESSION-HANDOFF.md — AI Agent 交接文件

> **用途**：此文件供 AI 開發代理在新會話中快速恢復專案狀態。
> **更新時機**：每次開發會話結束時由 AI 自動更新。
> **最後更新**：2026-04-25 20:28 (UTC+8)

---

## 🎯 目前的目標（Current Objective）
穩定化 AutoCAD 倉位自動化系統，解決因背景執行緒、遺失字體對話框或未清理的暫存檔所導致的 COM 拒絕呼叫 (`Call was rejected by callee` 或 `<unknown>.Open`) 問題。

---

## ✅ 已完成的工作（Completed Work）

### 最近一次開發週期（2026-04-25）

#### COM 通訊與防護網強化 (`app_ui.py`)
- **修正縮排與語法**：修復了嵌入式子程序字串中 `if ent_type in...` 的 `IndentationError` 以及其他語法問題，確保了 `py_compile` 和 `ast.parse` 測試通過。
- **實作輪詢機制**：將脆弱的 `time.sleep(2)` 寫法，改為 30 秒硬上限的 `while` 迴圈輪詢，主動檢查 `acad.ActiveDocument` 與 `doc.ModelSpace` 是否已就緒，避免 AutoCAD 在執行 `Regen` 時被 COM 誤認超時。
- **新增資源回收機制 (finally block)**：在 `parse_dwg_direct` 子程序中加入嚴格的 `try...finally` 區塊。確保無論發生什麼錯誤，都會呼叫 `doc.Close(False)` 和 `CoUninitialize()`，防止殭屍暫存檔殘留在 AutoCAD 記憶體中。

---

## 🔜 下一步行動（Next Steps）

### 高優先
1. `[x]` 確保 `auto_cad_worker.py` 的主流程也加入了 `try...finally` 的安全關閉機制（已透過修改腳本加入並以 0617AI.dwg 驗證成功）。
2. `[x]` 繼續推動 Google Drive OAuth 權限夾的自動化建立（已成功執行 setup_oauth_folders.py 並寫入目錄 IDs）。

### 中優先
3. `[x]` 對 `test_e2e_pipeline.py` 進行重新回歸測試，確認背景輪詢 Daemon 能夠在沒有人工干預的情況下連跑多張圖。

---

## ⚠️ 發現的地雷與決策（Discovered Gotchas）

### 🔴 嚴重
- **問題**：`Failed to open document: <unknown>.Open` 和 `Call was rejected by callee`。
- **後果**：導致整個應用程式與 AutoCAD 失去連線，甚至造成 AutoCAD 卡死（`IsQuiescent = False`）。
- **解法**：`<unknown>.Open` 是因為動態綁定 (Late Binding) 在 COM 處於 Busy 狀態時無法解析方法所拋出的錯誤，本質上就是被拒絕呼叫。根本原因是之前失敗的執行緒未呼叫 `doc.Close()`，導致大量 `tmpXXXX.dwg - 唯讀` 檔案堆積。解法是必須手動在 AutoCAD 內關閉所有殭屍圖檔，並在程式碼全面實作 `finally` 資源釋放。

### 🟢 架構決策
- 將 `acad.Documents.Open()` 的依賴弱化，改為主動輪詢 `acad.ActiveDocument` 以取得真實載入完成的 Document，這解決了不同版本 AutoCAD COM 開檔回傳值的差異問題。

---

## 📁 關鍵檔案索引
| 檔案 | 用途 |
|------|------|
| `app_ui.py` | Streamlit 網頁介面與 AutoCAD COM 通訊的核心橋樑 |
| `auto_cad_worker.py` | 負責實際的圖面實體解析、Ray Cast 碰撞計算與文字寫回邏輯 |
| `setup_oauth_folders.py` | （目前游標所在）用於初始化並綁定 Google Drive 的輸入/輸出資料夾 ID |

---

## 🔧 開發環境資訊
| 項目 | 值 |
|------|-----|
| 前端 Port | `8501` (Streamlit) |
| 目標軟體 | AutoCAD (Windows COM Object `AutoCAD.Application`) |
| 執行器 | `python -m streamlit run app_ui.py` |
