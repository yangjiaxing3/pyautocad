import json
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file('config/user_oauth_token.json', ['https://www.googleapis.com/auth/drive'])
service = build('drive', 'v3', credentials=creds)

PARENT_FOLDER_ID = "1W1dOlpX7toOhMfZVCSrHSoCbJbKVaFoB"

input_meta = {
    'name': 'AutoCAD_Input',
    'mimeType': 'application/vnd.google-apps.folder',
    'parents': ['1W1dOlpX7toOhMfZVCSrHSoCbJbKVaFoB']
}
output_meta = {
    'name': 'AutoCAD_Output',
    'mimeType': 'application/vnd.google-apps.folder',
    'parents': ['1W1dOlpX7toOhMfZVCSrHSoCbJbKVaFoB']
}

input_folder = service.files().create(body=input_meta, fields='id', supportsAllDrives=True).execute()
output_folder = service.files().create(body=output_meta, fields='id', supportsAllDrives=True).execute()

config = {
    'input_folder_id': input_folder['id'],
    'output_folder_id': output_folder['id'],
    'input_link': f"https://drive.google.com/drive/folders/{input_folder['id']}",
    'output_link': f"https://drive.google.com/drive/folders/{output_folder['id']}"
}
with open('config/drive_folders.json', 'w') as f:
    json.dump(config, f, indent=2)

print('CREATED NEW FOLDERS INSIDE TARGET DIRECTORY:')
print('INPUT:', config['input_link'])
print('OUTPUT:', config['output_link'])
