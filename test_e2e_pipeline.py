"""
test_e2e_pipeline.py
端到端測試腳本：上傳測試檔案 → 驗證 Watcher 下載 → 驗證 AutoCAD 處理 → 驗證輸出上傳

此腳本使用與 drive_watcher.py 相同的 OAuth 授權機制。
測試完後可以刪除 Google Drive 上的測試檔案。
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import os
import json
import time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ==========================================
# 設定
# ==========================================
SCOPES = ["https://www.googleapis.com/auth/drive"]
OAUTH_CLIENT_PATH = os.path.join("config", "oauth_client.json")
TOKEN_PATH = os.path.join("config", "user_oauth_token.json")

_cfg_path = os.path.join("config", "drive_folders.json")
if os.path.exists(_cfg_path):
    with open(_cfg_path, "r", encoding="utf-8") as f:
        _cfg = json.load(f)
    INPUT_FOLDER_ID = _cfg["input_folder_id"]
    OUTPUT_FOLDER_ID = _cfg["output_folder_id"]
else:
    INPUT_FOLDER_ID = "1GA0lFq1GBev2bQjolpGdfsQjOns-XI1Y"
    OUTPUT_FOLDER_ID = "17LdhwVz95mN_W2EQO01Suz2JWcxGBwbP"

# 測試檔案：使用「倉位不含編號.dwg」作為「新莊公園倉位無編號.dwg」
TEST_DWG = os.path.join("ref", "倉位不含編號.dwg")
UPLOAD_NAME = "新莊公園倉位無編號.dwg"


def get_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(OAUTH_CLIENT_PATH):
                print("❌ 找不到 " + OAUTH_CLIENT_PATH)
                print("   請先執行 setup 流程建立 OAuth 用戶端憑證。")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def main():
    print("=" * 60)
    print("🧪 端到端測試：AutoCAD 自動化管線")
    print("=" * 60)

    service = get_service()

    # Step 1: 驗證 Google Drive 資料夾存取
    print("\n--- Step 1: 驗證 Google Drive 資料夾存取 ---")
    for label, fid in [("INPUT", INPUT_FOLDER_ID), ("OUTPUT", OUTPUT_FOLDER_ID)]:
        try:
            folder = service.files().get(fileId=fid, fields="id, name", supportsAllDrives=True).execute()
            print("  " + label + " -> OK: " + folder["name"])
        except Exception as e:
            print("  " + label + " -> FAIL: " + str(e))
            sys.exit(1)

    # Step 2: 上傳測試 DWG 檔案
    print("\n--- Step 2: 上傳測試檔案至 INPUT 資料夾 ---")
    if not os.path.exists(TEST_DWG):
        print("  ❌ 測試檔案不存在: " + TEST_DWG)
        sys.exit(1)

    media = MediaFileUpload(TEST_DWG, mimetype="application/acad", resumable=True)
    file_metadata = {"name": UPLOAD_NAME, "parents": [INPUT_FOLDER_ID]}
    uploaded = service.files().create(body=file_metadata, media_body=media, fields="id, name", supportsAllDrives=True).execute()
    uploaded_id = uploaded["id"]
    print("  ✅ 上傳成功: " + uploaded["name"] + " (ID: " + uploaded_id + ")")

    # Step 3: 等待 Watcher 處理 (輪詢 OUTPUT 資料夾)
    print("\n--- Step 3: 等待 Watcher 處理 (最多 180 秒) ---")
    expected_output = UPLOAD_NAME.replace(".dwg", "_已編號.dwg")
    output_file_id = None

    for i in range(18):
        time.sleep(10)
        elapsed = (i + 1) * 10
        print("  等待中... " + str(elapsed) + "s")

        query = "'" + OUTPUT_FOLDER_ID + "' in parents and trashed = false"
        results = service.files().list(q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        for f in results.get("files", []):
            if expected_output in f["name"]:
                output_file_id = f["id"]
                print("  🎉 發現輸出檔案: " + f["name"] + " (ID: " + f["id"] + ")")
                break
        if output_file_id:
            break

    if not output_file_id:
        print("  ⚠️ 超時！未在 OUTPUT 資料夾中發現已處理的檔案。")
        print("     請確認 drive_watcher.py 正在執行中，且 AutoCAD 已啟動。")
    else:
        print("\n  ✅ 端到端測試通過！完整流程驗證成功！")

    # Step 4: 清理測試檔案
    print("\n--- Step 4: 清理測試檔案 ---")
    try:
        service.files().delete(fileId=uploaded_id, supportsAllDrives=True).execute()
        print("  ✅ 已刪除 INPUT 測試檔案")
    except Exception as e:
        print("  ⚠️ 刪除 INPUT 檔案失敗: " + str(e))

    if output_file_id:
        try:
            service.files().delete(fileId=output_file_id, supportsAllDrives=True).execute()
            print("  ✅ 已刪除 OUTPUT 測試檔案")
        except Exception as e:
            print("  ⚠️ 刪除 OUTPUT 檔案失敗: " + str(e))

    print("\n" + "=" * 60)
    print("🏁 測試完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
