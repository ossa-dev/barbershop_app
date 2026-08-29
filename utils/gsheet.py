"""
Koneksi & operasi ke Google Sheets (dipakai sebagai database relasional sederhana).
Membutuhkan st.secrets['gcp_service_account'] dan st.secrets['SPREADSHEET_ID'].
"""
from typing import Optional

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

from utils.format_utils import now_wib

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_KARYAWAN = "Data_Karyawan"
SHEET_ABSENSI = "Log_Absensi"
SHEET_KEUANGAN = "Keuangan"

HEADERS = {
    SHEET_KARYAWAN: ["Nama", "PIN", "Status"],
    SHEET_ABSENSI: ["Waktu", "Nama", "Status", "Link Foto Drive"],
    SHEET_KEUANGAN: ["Tanggal", "Jenis", "Nominal", "Keterangan"],
}


@st.cache_resource(show_spinner=False)
def _get_client() -> gspread.Client:
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=SCOPES
    )
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def _get_spreadsheet():
    client = _get_client()
    return client.open_by_key(st.secrets["SPREADSHEET_ID"])


def ensure_sheet_structure():
    """
    Pastikan 3 tab (Data_Karyawan, Log_Absensi, Keuangan) ada beserta header-nya.
    Aman dipanggil berkali-kali (idempotent) -- dijalankan otomatis saat app start.
    """
    ss = _get_spreadsheet()
    existing = {ws.title: ws for ws in ss.worksheets()}
    for nama_tab, header in HEADERS.items():
        if nama_tab not in existing:
            ws = ss.add_worksheet(title=nama_tab, rows=1000, cols=len(header))
            ws.append_row(header)
        else:
            ws = existing[nama_tab]
            first_row = ws.row_values(1)
            if first_row != header:
                ws.update("A1", [header])


def _get_ws(nama_tab: str):
    return _get_spreadsheet().worksheet(nama_tab)


def _get_df(nama_tab: str) -> pd.DataFrame:
    ws = _get_ws(nama_tab)
    data = ws.get_all_records()
    return pd.DataFrame(data)


# ---------- Data_Karyawan ----------

def get_karyawan_aktif() -> list:
    df = _get_df(SHEET_KARYAWAN)
    if df.empty:
        return []
    df["Status"] = df["Status"].astype(str).str.strip().str.lower()
    aktif = df[df["Status"] == "aktif"]
    return aktif["Nama"].astype(str).tolist()


def verifikasi_pin(nama: str, pin: str) -> bool:
    df = _get_df(SHEET_KARYAWAN)
    if df.empty:
        return False
    df["PIN"] = df["PIN"].astype(str).str.strip()
    cocok = df[(df["Nama"] == nama) & (df["PIN"] == str(pin).strip())]
    return not cocok.empty


# ---------- Log_Absensi ----------

def status_absen_berikutnya(nama: str) -> Optional[str]:
    """
    Menentukan apakah absen berikutnya untuk `nama` adalah 'Masuk' atau 'Pulang'.
    Mengembalikan None jika hari ini sudah lengkap (Masuk & Pulang tercatat).
    """
    df = _get_df(SHEET_ABSENSI)
    if df.empty:
        return "Masuk"
    hari_ini = now_wib().strftime("%d-%m-%Y")
    df["_tgl"] = df["Waktu"].astype(str).str[:10]
    log_hari_ini = df[(df["Nama"] == nama) & (df["_tgl"] == hari_ini)]
    status_tercatat = set(log_hari_ini["Status"].astype(str))
    if "Masuk" not in status_tercatat:
        return "Masuk"
    if "Pulang" not in status_tercatat:
        return "Pulang"
    return None


def catat_absensi(nama: str, status: str, link_foto: str):
    ws = _get_ws(SHEET_ABSENSI)
    waktu = now_wib().strftime("%d-%m-%Y %H:%M:%S")
    ws.append_row([waktu, nama, status, link_foto])


def get_absensi_df() -> pd.DataFrame:
    return _get_df(SHEET_ABSENSI)


# ---------- Keuangan ----------

def catat_keuangan(tanggal: str, jenis: str, nominal: float, keterangan: str):
    ws = _get_ws(SHEET_KEUANGAN)
    ws.append_row([tanggal, jenis, nominal, keterangan])


def get_keuangan_df() -> pd.DataFrame:
    return _get_df(SHEET_KEUANGAN)
