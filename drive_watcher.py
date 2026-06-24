import os
import io
import time
import json
import sqlite3
import sys
import traceback
import subprocess
import logging
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# NOTE: 修復 Windows cp950 無法印出 emoji 的問題
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ==========================================
# ⚙️ 設定區
# ==========================================
# NOTE: 優先從 config/drive_folders.json 讀取資料夾 ID
_drive_cfg_path = os.path.join("config", "drive_folders.json")
if os.path.exists(_drive_cfg_path):
    with open(_drive_cfg_path, "r", encoding="utf-8") as _f:
        _drive_cfg = json.load(_f)
    INPUT_FOLDER_ID = _drive_cfg["input_folder_id"]
    OUTPUT_FOLDER_ID = _drive_cfg["output_folder_id"]
else:
    # 退回硬編碼值
    INPUT_FOLDER_ID = "1GA0lFq1GBev2bQjolpGdfsQjOns-XI1Y"
    OUTPUT_FOLDER_ID = "17LdhwVz95mN_W2EQO01Suz2JWcxGBwbP"

SCOPES = ['https://www.googleapis.com/auth/drive']
DB_PATH = "processed_files.db"
# NOTE: OAuth 用戶端檔案路徑 — 使用者本人帳號授權
OAUTH_CLIENT_PATH = os.path.join("config", "oauth_client.json")
TOKEN_PATH = os.path.join("config", "user_oauth_token.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ==========================================
# 🗄️ SQLite Idempotency (Durable Execution)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS processed_files
                 (file_id TEXT PRIMARY KEY, filename TEXT, processed_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def is_processed(file_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM processed_files WHERE file_id = ?", (file_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def mark_processed(file_id, filename):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO processed_files (file_id, filename) VALUES (?, ?)", (file_id, filename))
    conn.commit()
    conn.close()

# ==========================================
# 🌐 Google Drive Auth (OAuth — 使用者帳號)
# ==========================================
def get_gdrive_service():
    """
    取得以使用者身份授權的 Google Drive API 服務。
    首次執行會彈出瀏覽器讓使用者登入，之後使用 refresh token 自動刷新。
    """
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("🔄 Token 已過期，自動刷新中...")
            creds.refresh(Request())
        else:
            if not os.path.exists(OAUTH_CLIENT_PATH):
                logger.error(f"❌ 找不到 {OAUTH_CLIENT_PATH}！")
                logger.error("  請到 Google Cloud Console -> APIs & Services -> Credentials")
                logger.error("  建立 OAuth 2.0 Client ID (Desktop app)，下載 JSON 後")
                logger.error(f"  重新命名為 oauth_client.json 並放入 config/ 目錄。")
                raise FileNotFoundError(OAUTH_CLIENT_PATH)

            logger.info("🌐 首次授權，即將彈出瀏覽器視窗...")
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        # 儲存 token 以便後續自動刷新
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
        logger.info("✅ Token 已儲存至 " + TOKEN_PATH)

    return build('drive', 'v3', credentials=creds)

# ==========================================
# 🛠️ AutoCAD Worker Invocation
# ==========================================
def run_autocad_worker(dwg_path):
    """
    呼叫獨立的 AutoCAD Worker 腳本 (避免 COM 執行緒死鎖)
    回傳: (成功與否, 處理後的檔案路徑或錯誤訊息)
    """
    worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_cad_worker.py")
    out_dwg_path = dwg_path.replace(".dwg", "_processed.dwg")

    cmd = [sys.executable, worker_script, dwg_path, out_dwg_path]
    logger.info("啟動 AutoCAD Worker: " + " ".join(cmd))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return False, "Worker 執行逾時 (600s)"

    stdout = result.stdout.strip()
    if result.returncode == 0 and "SUCCESS" in stdout and os.path.exists(out_dwg_path):
        return True, out_dwg_path
    else:
        return False, "Worker 失敗:\nSTDOUT: " + result.stdout + "\nSTDERR: " + result.stderr

# ==========================================
# 🔄 Main Event Loop
# ==========================================
def main_loop():
    init_db()
    service = get_gdrive_service()
    logger.info("✅ Google Drive Watcher 已啟動 (OAuth Mode)，開始輪詢...")
    logger.info("   INPUT:  " + INPUT_FOLDER_ID)
    logger.info("   OUTPUT: " + OUTPUT_FOLDER_ID)

    error_count = 0
    while True:
        try:
            # 1. 搜尋輸入資料夾中的未處理檔案 (.dwg)
            query = "'" + INPUT_FOLDER_ID + "' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
            results = service.files().list(q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
            items = results.get('files', [])

            for item in items:
                file_id = item['id']
                filename = item['name']

                if not filename.lower().endswith(".dwg"):
                    continue

                if is_processed(file_id):
                    continue

                logger.info("📥 發現新任務: " + filename + " (ID: " + file_id + ")")

                # 2. 下載檔案
                request = service.files().get_media(fileId=file_id)
                local_path = os.path.join("tmp", filename)
                os.makedirs("tmp", exist_ok=True)

                with open(local_path, "wb") as fh:
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                        pct = int(status.progress() * 100)
                        logger.info("Downloading " + filename + "... " + str(pct) + "%")

                # 3. 處理 DWG (AutoCAD COM)
                logger.info("⚙️ 開始透過 AutoCAD 處理 " + filename + "...")
                success, out_path_or_err = run_autocad_worker(local_path)

                if not success:
                    logger.error("❌ 處理 " + filename + " 失敗: " + out_path_or_err)
                    # NOTE: 標記為已處理以避免無限重試損壞檔案
                    mark_processed(file_id, filename + " [FAILED]")
                    continue

                # 4. 上傳至 Output Folder
                logger.info("📤 處理完成，上傳至輸出目錄...")
                output_name = filename.replace(".dwg", "_已編號.dwg")
                media = MediaFileUpload(out_path_or_err, mimetype='application/acad', resumable=True)
                file_metadata = {
                    'name': output_name,
                    'parents': [OUTPUT_FOLDER_ID]
                }
                uploaded_file = service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=True).execute()
                logger.info("✅ DWG 任務完成: " + output_name + " -> " + uploaded_file.get('id'))

                # 上傳 Excel 報表
                excel_local = out_path_or_err.replace(".dwg", ".xlsx")
                if os.path.exists(excel_local):
                    excel_name = filename.replace(".dwg", "_報表.xlsx")
                    media_xl = MediaFileUpload(excel_local, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', resumable=True)
                    xl_meta = {
                        'name': excel_name,
                        'parents': [OUTPUT_FOLDER_ID]
                    }
                    xl_file = service.files().create(body=xl_meta, media_body=media_xl, fields='id', supportsAllDrives=True).execute()
                    logger.info("✅ EXCEL 任務完成: " + excel_name + " -> " + xl_file.get('id'))

                # 5. 標記為已處理 (Idempotency)
                mark_processed(file_id, filename)

                # 清理本機暫存
                for p in [local_path, out_path_or_err, excel_local]:
                    try:
                        os.remove(p)
                    except Exception:
                        pass

            # 成功執行，重置錯誤計數
            error_count = 0

        except Exception as e:
            logger.error("⚠️ 輪詢發生錯誤: " + str(e))
            traceback.print_exc()
            error_count += 1

        # Exponential Backoff for polling (10s -> 20s -> 40s, max 60s)
        sleep_time = min(60, 10 * (2 ** min(error_count, 3)))
        time.sleep(sleep_time)

if __name__ == "__main__":
    main_loop()
