---
name: "multi-agent-mode"
description: "啟動多 Agent 模式。Invoke when user asks for '多agent 模式', 'multi-agent mode', or requests a multi-stage review and implementation process."
---

# 多 Agent 模式 (Multi-Agent Mode)

當使用者啟動「多 Agent 模式」或「多agent 模式」時，請嚴格按照以下五個 Agent 的角色與流程循序執行任務：

## 執行流程

### 1. Agent A: 優化方案發想
- **任務**：針對使用者的需求或當前程式碼，進行腦力激盪，提出多種可能的優化方案、架構設計或實作方向。
- **產出**：具體的方案清單與各方案的優缺點分析。

### 2. Agent B: 高度質疑模式 (Red Teaming)
- **任務**：以極度嚴苛和批判的視角，審查 Agent A 提出的方案。
- **重點**：找出潛在的 bugs、邊界情況 (edge cases)、效能瓶頸、不合理之處，以及任何可以進一步優化的細節。
- **產出**：針對每個方案的質疑報告與風險評估。

### 3. Agent C: 意見整合與最終方案提出
- **任務**：綜合 Agent A 的創新發想與 Agent B 的批判質疑。
- **重點**：解決 B 提出的所有問題，過濾掉不切實際的想法，並梳理出一個最穩健、高效且可行的「整合方案」。
- **產出**：最終確認的實作計畫 (Action Plan) 或架構藍圖。

### 4. Agent D: 開始進行製作 (Implementation)
- **任務**：根據 Agent C 提出的整合方案，實際動手撰寫程式碼或進行修改。
- **重點**：嚴格遵守方案細節與專案既有的 coding style，確保程式碼的完整性。
- **產出**：完成實作的程式碼檔案或修改差異 (Diff)。

### 5. Agent E: Code Review 和驗證
- **任務**：對 Agent D 產出的程式碼進行最終審查與測試驗證。
- **重點**：確認程式碼是否完全符合需求、是否引入了新的錯誤，並在必要時建議補充測試案例。
- **產出**：最終的 Review 報告；若有問題則退回給 Agent D 修正，若無問題則向使用者回報任務完成。

## 執行規則
- 你（AI 助手）需要在此模式下，依序**扮演**這五個 Agent 的角色。
- 在切換每個 Agent 角色時，請明確標示當前正在執行的 Agent（例如：`### 🤖 Agent A: 優化方案發想`），讓使用者清楚目前的進度。
- 若任務過於龐大，可以在 Agent C 產出整合方案後，先暫停並詢問使用者是否同意該方案（使用 `AskUserQuestion` 或直接等待回覆），待確認後再交由 Agent D 進行製作。
