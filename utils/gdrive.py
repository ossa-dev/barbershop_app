"""
Koneksi & operasi ke Google Drive: mencari/membuat struktur folder berjenjang
(Absensi / <tahun> / <bulan>) di dalam SHARED DRIVE, dan mengunggah foto absensi.

PENTING: Service account TIDAK punya storage quota di "My Drive"-nya sendiri,
jadi semua folder & file harus dibuat di dalam Shared Drive (Drive Bersama)
tempat service account ditambahkan sebagai anggota (Content Manager/Manager).

Tambahkan di st.secrets:
    SHARED_DRIVE_ID = "xxxxxxxxxxxxxxxxxxxx"   # id Shared Drive, dari URL setelah /folders/
"""
import io
from typing import Optional

import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from utils.format_utils import nama_folder_bulan, now_wib

SCOPES = ["https://www.googleapis.com/auth/drive"]
ABSENSI_FOLDER_NAME = "absensi"


@st.cache_resource(show_spinner=False)
def _get_service():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _shared_drive_id() -> str:
    return st.secrets["SHARED_DRIVE_ID"]


def _cari_folder(service, nama: str, parent_id: str) -> Optional[str]:
    query = (
        f"name = '{nama}' and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false and '{parent_id}' in parents"
    )
    hasil = (
        service.files()
        .list(
            q=query,
            spaces="drive",
            fields="files(id, name)",
            corpora="drive",
            driveId=_shared_drive_id(),
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        )
        .execute()
    )
    files = hasil.get("files", [])
    return files[0]["id"] if files else None


def _buat_folder(service, nama: str, parent_id: str) -> str:
    metadata = {
        "name": nama,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = (
        service.files()
        .create(body=metadata, fields="id", supportsAllDrives=True)
        .execute()
    )
    return folder["id"]


def _cari_atau_buat_folder(service, nama: str, parent_id: str) -> str:
    folder_id = _cari_folder(service, nama, parent_id)
    if folder_id:
        return folder_id
    return _buat_folder(service, nama, parent_id)


def get_folder_absensi_bulan_ini() -> str:
    """Kembalikan folder id untuk Absensi/<tahun>/<bulan> di dalam Shared Drive,
    membuat jika belum ada."""
    service = _get_service()
    root_id = _shared_drive_id()  # root folder = Shared Drive itu sendiri
    absensi_id = _cari_atau_buat_folder(service, ABSENSI_FOLDER_NAME, root_id)
    tahun_id = _cari_atau_buat_folder(service, str(now_wib().year), absensi_id)
    bulan_id = _cari_atau_buat_folder(service, nama_folder_bulan(), tahun_id)
    return bulan_id


def upload_foto(file_bytes: bytes, filename: str, folder_id: str) -> str:
    """Unggah foto (JPEG) ke folder_id, buat bisa dibuka via link, kembalikan link."""
    service = _get_service()
    metadata = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype="image/jpeg", resumable=False)
    file = (
        service.files()
        .create(
            body=metadata,
            media_body=media,
            fields="id, webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )

    # Supaya link yang disimpan di Google Sheets bisa langsung dibuka (preview JPEG native)
    try:
        service.permissions().create(
            fileId=file["id"],
            body={"role": "reader", "type": "anyone"},
            supportsAllDrives=True,
        ).execute()
    except Exception:
        pass  # kalau gagal set permission publik, link tetap tersimpan -> share manual dari Drive

    return file.get("webViewLink", f"https://drive.google.com/file/d/{file['id']}/view")