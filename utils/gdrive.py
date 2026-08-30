"""
Koneksi & operasi ke Google Drive: mencari/membuat struktur folder berjenjang
(zza_barbershop / absensi / <tahun> / <bulan>) dan mengunggah foto absensi.

PENTING - kenapa pakai OAuth akun Gmail pribadi (bukan service account):
Service account TIDAK punya kuota penyimpanan Drive sendiri (0 GB), dan
Shared Drive (yang biasanya jadi solusi) hanya tersedia untuk akun
Google Workspace, bukan Gmail pribadi. Jadi solusi untuk Gmail pribadi
adalah membuat file "dimiliki" oleh akun Gmail-mu sendiri lewat OAuth
refresh token (dibuat sekali lewat get_refresh_token.py), sehingga foto
memakai kuota gratis 15GB akun Gmail-mu.

Perlu di st.secrets:
    [gdrive_oauth]
    client_id = "..."
    client_secret = "..."
    refresh_token = "..."
"""
import io
from typing import Optional

import streamlit as st
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from utils.format_utils import nama_folder_bulan, now_wib

SCOPES = ["https://www.googleapis.com/auth/drive"]
ROOT_FOLDER_NAME = "zza_barbershop"
ABSENSI_FOLDER_NAME = "absensi"
TOKEN_URI = "https://oauth2.googleapis.com/token"


@st.cache_resource(show_spinner=False)
def _get_service():
    cfg = st.secrets["gdrive_oauth"]
    creds = Credentials(
        token=None,
        refresh_token=cfg["refresh_token"],
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _cari_folder(service, nama: str, parent_id: Optional[str]) -> Optional[str]:
    query = (
        f"name = '{nama}' and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"
    hasil = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    files = hasil.get("files", [])
    return files[0]["id"] if files else None


def _buat_folder(service, nama: str, parent_id: Optional[str]) -> str:
    metadata = {"name": nama, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def _cari_atau_buat_folder(service, nama: str, parent_id: Optional[str] = None) -> str:
    folder_id = _cari_folder(service, nama, parent_id)
    if folder_id:
        return folder_id
    return _buat_folder(service, nama, parent_id)


@st.cache_resource(show_spinner=False)
def _get_root_folder_id() -> str:
    service = _get_service()
    return _cari_atau_buat_folder(service, ROOT_FOLDER_NAME, None)


def get_folder_absensi_bulan_ini() -> str:
    """Kembalikan folder id untuk Absensi/<tahun>/<bulan>, membuat jika belum ada."""
    service = _get_service()
    root_id = _get_root_folder_id()
    absensi_id = _cari_atau_buat_folder(service, ABSENSI_FOLDER_NAME, root_id)
    tahun_id = _cari_atau_buat_folder(service, str(now_wib().year), absensi_id)
    bulan_id = _cari_atau_buat_folder(service, nama_folder_bulan(), tahun_id)
    return bulan_id


def upload_foto(file_bytes: bytes, filename: str, folder_id: str) -> str:
    """Unggah foto (JPEG) ke folder_id, buat bisa dibuka via link, kembalikan link."""
    service = _get_service()
    metadata = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype="image/jpeg", resumable=False)
    file = service.files().create(body=metadata, media_body=media, fields="id, webViewLink").execute()

    # Supaya link yang disimpan di Google Sheets bisa langsung dibuka (preview JPEG native)
    try:
        service.permissions().create(
            fileId=file["id"], body={"role": "reader", "type": "anyone"}
        ).execute()
    except Exception:
        pass  # kalau gagal set permission publik, link tetap tersimpan -> share manual dari Drive

    return file.get("webViewLink", f"https://drive.google.com/file/d/{file['id']}/view")