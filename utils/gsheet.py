"""
Koneksi & operasi ke Google Sheets (dipakai sebagai database relasional sederhana).
Membutuhkan st.secrets['gcp_service_account'] dan st.secrets['SPREADSHEET_ID'].
"""
from datetime import datetime, timedelta
from typing import Optional

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

from utils.format_utils import WIB, now_wib

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ---------- Nama tab ----------
SHEET_KARYAWAN = "Data_Karyawan"
SHEET_ABSENSI = "Log_Absensi"
SHEET_KEUANGAN = "Keuangan"
SHEET_JASA = "Master_Jasa"
SHEET_BAHAN = "Master_Bahan"
SHEET_RESEP = "Resep_Jasa"
SHEET_TRANSAKSI = "Log_Transaksi"
SHEET_PEMBELIAN = "Log_Pembelian_Bahan"
SHEET_TUTUP_KAS = "Tutup_Kas"
SHEET_STOK_OPNAME = "Stok_Opname"
SHEET_UTANG = "Utang_Selisih"

HEADERS = {
    SHEET_KARYAWAN: ["Nama", "PIN", "Status", "Boleh_Restock", "Percobaan_Gagal", "Terkunci_Sampai"],
    SHEET_ABSENSI: ["Waktu", "Nama", "Status", "Link Foto Drive"],
    SHEET_KEUANGAN: ["Tanggal", "Jenis", "Nominal", "Keterangan"],
    SHEET_JASA: ["Nama_Jasa", "Harga", "Status"],
    SHEET_BAHAN: ["Nama_Bahan", "Satuan", "Stok_Saat_Ini", "Stok_Minimum", "Status"],
    SHEET_RESEP: ["Nama_Jasa", "Nama_Bahan", "Jumlah_Terpakai"],
    SHEET_TRANSAKSI: ["ID_Transaksi", "Waktu", "Karyawan", "Nama_Jasa", "Harga", "Metode_Bayar", "Nama_Pelanggan"],
    SHEET_PEMBELIAN: ["Waktu", "Karyawan", "Nama_Bahan", "Jumlah", "Total_Harga"],
    SHEET_TUTUP_KAS: ["Waktu", "Karyawan", "Tanggal", "Total_Tunai_Sistem", "Total_Tunai_Fisik", "Selisih"],
    SHEET_STOK_OPNAME: ["Waktu", "Nama_Bahan", "Stok_Sistem", "Stok_Fisik", "Selisih", "Keterangan"],
    SHEET_UTANG: ["Waktu", "Karyawan", "Sumber", "Jumlah", "Status_Lunas", "Keterangan"],
}

MAKS_PERCOBAAN_PIN = 5
DURASI_LOCKOUT_MENIT = 15
BATAS_DUPLIKAT_DETIK = 10


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


@st.cache_resource(show_spinner=False)
def ensure_sheet_structure():
    """
    Pastikan semua tab (termasuk yang baru) ada beserta header-nya.
    Di-cache dengan cache_resource supaya HANYA jalan sekali per proses app,
    bukan setiap kali Streamlit rerun script (tiap klik/isi form = rerun).
    Kalau skema sheet berubah manual di Google Sheets dan perlu dicek ulang,
    restart aplikasi Streamlit-nya (cache_resource ke-reset saat proses baru).
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


def _cari_baris_ke(df: pd.DataFrame, kondisi) -> Optional[int]:
    """Nomor baris di sheet (termasuk header) untuk baris pertama yang cocok, atau None."""
    idx = df.index[kondisi]
    if idx.empty:
        return None
    return int(idx[0]) + 2  # +1 karena header, +1 lagi karena index dimulai dari 0


def _kolom_ke(nama_tab: str, nama_kolom: str) -> int:
    return HEADERS[nama_tab].index(nama_kolom) + 1


# ================= Data_Karyawan =================

@st.cache_data(ttl=30, show_spinner=False)
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


@st.cache_data(ttl=30, show_spinner=False)
def boleh_restock(nama: str) -> bool:
    df = _get_df(SHEET_KARYAWAN)
    if df.empty:
        return False
    baris = df[df["Nama"] == nama]
    if baris.empty:
        return False
    nilai = str(baris.iloc[0].get("Boleh_Restock", "")).strip().lower()
    return nilai in ("true", "ya", "yes", "1")


@st.cache_data(ttl=10, show_spinner=False)
def cek_lockout(nama: str):
    """Kembalikan (terkunci: bool, pesan: str atau None)."""
    df = _get_df(SHEET_KARYAWAN)
    if df.empty:
        return False, None
    baris = df[df["Nama"] == nama]
    if baris.empty:
        return False, None
    terkunci_sampai = str(baris.iloc[0].get("Terkunci_Sampai", "")).strip()
    if not terkunci_sampai:
        return False, None
    try:
        waktu_buka = datetime.strptime(terkunci_sampai, "%d-%m-%Y %H:%M").replace(tzinfo=WIB)
    except ValueError:
        return False, None
    sekarang = now_wib()
    if sekarang < waktu_buka:
        sisa_menit = int((waktu_buka - sekarang).total_seconds() // 60) + 1
        return True, f"Akun terkunci karena terlalu banyak PIN salah. Coba lagi dalam {sisa_menit} menit."
    return False, None


def catat_pin_salah(nama: str) -> dict:
    """
    Tambah hitungan percobaan gagal. Kalau sudah mencapai batas, aktifkan lockout.
    Kembalikan dict {"terkunci": bool, "sisa_percobaan": int, "pesan": str}.
    """
    ws = _get_ws(SHEET_KARYAWAN)
    df = _get_df(SHEET_KARYAWAN)
    baris_ke = _cari_baris_ke(df, df["Nama"] == nama)
    if baris_ke is None:
        return {"terkunci": False, "sisa_percobaan": MAKS_PERCOBAAN_PIN, "pesan": "PIN salah."}

    percobaan_lama = df.loc[df["Nama"] == nama, "Percobaan_Gagal"].iloc[0]
    try:
        percobaan_lama = int(percobaan_lama)
    except (TypeError, ValueError):
        percobaan_lama = 0
    percobaan_baru = percobaan_lama + 1

    kolom_percobaan = _kolom_ke(SHEET_KARYAWAN, "Percobaan_Gagal")
    ws.update_cell(baris_ke, kolom_percobaan, percobaan_baru)
    get_karyawan_aktif.clear()
    cek_lockout.clear()

    if percobaan_baru >= MAKS_PERCOBAAN_PIN:
        waktu_buka = now_wib() + timedelta(minutes=DURASI_LOCKOUT_MENIT)
        kolom_lockout = _kolom_ke(SHEET_KARYAWAN, "Terkunci_Sampai")
        ws.update_cell(baris_ke, kolom_lockout, waktu_buka.strftime("%d-%m-%Y %H:%M"))
        ws.update_cell(baris_ke, kolom_percobaan, 0)
        cek_lockout.clear()
        return {
            "terkunci": True,
            "sisa_percobaan": 0,
            "pesan": f"PIN salah {MAKS_PERCOBAAN_PIN} kali. Akun terkunci selama {DURASI_LOCKOUT_MENIT} menit.",
        }

    sisa = MAKS_PERCOBAAN_PIN - percobaan_baru
    return {"terkunci": False, "sisa_percobaan": sisa, "pesan": f"PIN salah. Sisa percobaan: {sisa}."}


def reset_pin_salah(nama: str):
    ws = _get_ws(SHEET_KARYAWAN)
    df = _get_df(SHEET_KARYAWAN)
    baris_ke = _cari_baris_ke(df, df["Nama"] == nama)
    if baris_ke is None:
        return
    ws.update_cell(baris_ke, _kolom_ke(SHEET_KARYAWAN, "Percobaan_Gagal"), 0)
    ws.update_cell(baris_ke, _kolom_ke(SHEET_KARYAWAN, "Terkunci_Sampai"), "")
    cek_lockout.clear()


# ================= Log_Absensi =================

@st.cache_data(ttl=10, show_spinner=False)
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
    get_absensi_df.clear()
    status_absen_berikutnya.clear()


@st.cache_data(ttl=30, show_spinner=False)
def get_absensi_df() -> pd.DataFrame:
    return _get_df(SHEET_ABSENSI)


def karyawan_sedang_shift() -> list:
    """Nama karyawan yang sudah Masuk hari ini tapi belum Pulang (untuk reminder owner).
    Pakai get_absensi_df() (cached) -- data yang sama persis sudah ditarik dengan aman
    di baris 'Riwayat Absensi' dashboard, tidak perlu baca sheet dua kali."""
    df = get_absensi_df()
    if df.empty:
        return []
    hari_ini = now_wib().strftime("%d-%m-%Y")
    df["_tgl"] = df["Waktu"].astype(str).str[:10]
    df_hari_ini = df[df["_tgl"] == hari_ini]
    sedang_shift = []
    for nama in df_hari_ini["Nama"].unique():
        status_nama = set(df_hari_ini[df_hari_ini["Nama"] == nama]["Status"].astype(str))
        if "Masuk" in status_nama and "Pulang" not in status_nama:
            sedang_shift.append(nama)
    return sedang_shift


# ================= Keuangan (umum, di luar transaksi jasa) =================

def catat_keuangan(tanggal: str, jenis: str, nominal: float, keterangan: str):
    ws = _get_ws(SHEET_KEUANGAN)
    ws.append_row([tanggal, jenis, nominal, keterangan])
    get_keuangan_df.clear()


@st.cache_data(ttl=30, show_spinner=False)
def get_keuangan_df() -> pd.DataFrame:
    return _get_df(SHEET_KEUANGAN)


# ================= Master_Jasa =================

@st.cache_data(ttl=30, show_spinner=False)
def get_jasa_aktif() -> pd.DataFrame:
    df = _get_df(SHEET_JASA)
    if df.empty:
        return df
    df["Status"] = df["Status"].astype(str).str.strip().str.lower()
    return df[df["Status"] == "aktif"].reset_index(drop=True)


@st.cache_data(ttl=30, show_spinner=False)
def get_master_jasa_df() -> pd.DataFrame:
    return _get_df(SHEET_JASA)


def _harga_jasa_fresh(nama_jasa: str) -> float:
    """
    Baca harga langsung dari sheet TANPA cache. Dipakai saat transaksi benar-benar
    disimpan (snapshot), supaya harga yang tercatat selalu akurat -- tidak mungkin
    ikut basi gara-gara cache yang dipakai untuk tampilan preview di UI.
    """
    df = _get_df(SHEET_JASA)
    baris = df[df["Nama_Jasa"] == nama_jasa]
    if baris.empty:
        return 0
    try:
        return float(baris.iloc[0]["Harga"])
    except (TypeError, ValueError):
        return 0


@st.cache_data(ttl=30, show_spinner=False)
def harga_jasa(nama_jasa: str) -> float:
    """Untuk tampilan preview harga di UI (boleh sedikit basi, cache 30 detik)."""
    return _harga_jasa_fresh(nama_jasa)


def tambah_jasa(nama_jasa: str, harga: float):
    ws = _get_ws(SHEET_JASA)
    ws.append_row([nama_jasa, harga, "Aktif"])
    get_jasa_aktif.clear()
    get_master_jasa_df.clear()
    harga_jasa.clear()


def ubah_status_jasa(nama_jasa: str, status_baru: str):
    ws = _get_ws(SHEET_JASA)
    df = _get_df(SHEET_JASA)
    baris_ke = _cari_baris_ke(df, df["Nama_Jasa"] == nama_jasa)
    if baris_ke is None:
        return
    ws.update_cell(baris_ke, _kolom_ke(SHEET_JASA, "Status"), status_baru)
    get_jasa_aktif.clear()
    get_master_jasa_df.clear()


# ================= Master_Bahan =================

@st.cache_data(ttl=30, show_spinner=False)
def get_bahan_aktif() -> pd.DataFrame:
    df = _get_df(SHEET_BAHAN)
    if df.empty:
        return df
    df["Status"] = df["Status"].astype(str).str.strip().str.lower()
    return df[df["Status"] == "aktif"].reset_index(drop=True)


@st.cache_data(ttl=30, show_spinner=False)
def get_master_bahan_df() -> pd.DataFrame:
    return _get_df(SHEET_BAHAN)


def tambah_bahan(nama_bahan: str, satuan: str, stok_awal: float, stok_minimum: float):
    ws = _get_ws(SHEET_BAHAN)
    ws.append_row([nama_bahan, satuan, stok_awal, stok_minimum, "Aktif"])
    get_bahan_aktif.clear()
    get_master_bahan_df.clear()


def ubah_status_bahan(nama_bahan: str, status_baru: str):
    ws = _get_ws(SHEET_BAHAN)
    df = _get_df(SHEET_BAHAN)
    baris_ke = _cari_baris_ke(df, df["Nama_Bahan"] == nama_bahan)
    if baris_ke is None:
        return
    ws.update_cell(baris_ke, _kolom_ke(SHEET_BAHAN, "Status"), status_baru)
    get_bahan_aktif.clear()
    get_master_bahan_df.clear()


def stok_bahan_sekarang(nama_bahan: str) -> float:
    df = _get_df(SHEET_BAHAN)
    baris = df[df["Nama_Bahan"] == nama_bahan]
    if baris.empty:
        return 0
    try:
        return float(baris.iloc[0]["Stok_Saat_Ini"])
    except (TypeError, ValueError):
        return 0


def _ubah_stok_bahan(nama_bahan: str, selisih: float):
    """Tambah (atau kurangi kalau selisih negatif) Stok_Saat_Ini untuk satu bahan."""
    ws = _get_ws(SHEET_BAHAN)
    df = _get_df(SHEET_BAHAN)
    baris = df[df["Nama_Bahan"] == nama_bahan]
    if baris.empty:
        return
    baris_ke = int(baris.index[0]) + 2
    try:
        stok_lama = float(baris.iloc[0]["Stok_Saat_Ini"])
    except (TypeError, ValueError):
        stok_lama = 0
    stok_baru = stok_lama + selisih
    ws.update_cell(baris_ke, _kolom_ke(SHEET_BAHAN, "Stok_Saat_Ini"), stok_baru)
    get_bahan_aktif.clear()
    get_master_bahan_df.clear()


@st.cache_data(ttl=30, show_spinner=False)
def bahan_stok_menipis() -> pd.DataFrame:
    df = get_bahan_aktif()
    if df.empty:
        return df
    df = df.copy()
    df["Stok_Saat_Ini"] = pd.to_numeric(df["Stok_Saat_Ini"], errors="coerce").fillna(0)
    df["Stok_Minimum"] = pd.to_numeric(df["Stok_Minimum"], errors="coerce").fillna(0)
    return df[df["Stok_Saat_Ini"] <= df["Stok_Minimum"]]


# ================= Resep_Jasa =================

@st.cache_data(ttl=30, show_spinner=False)
def get_resep_df() -> pd.DataFrame:
    return _get_df(SHEET_RESEP)


def get_resep_untuk_jasa(nama_jasa: str) -> pd.DataFrame:
    df = get_resep_df()
    if df.empty:
        return df
    return df[df["Nama_Jasa"] == nama_jasa]


def tambah_resep(nama_jasa: str, nama_bahan: str, jumlah: float):
    ws = _get_ws(SHEET_RESEP)
    ws.append_row([nama_jasa, nama_bahan, jumlah])
    get_resep_df.clear()


def hapus_resep(nama_jasa: str, nama_bahan: str):
    ws = _get_ws(SHEET_RESEP)
    df = _get_df(SHEET_RESEP)
    baris_ke = _cari_baris_ke(df, (df["Nama_Jasa"] == nama_jasa) & (df["Nama_Bahan"] == nama_bahan))
    if baris_ke is None:
        return
    ws.delete_rows(baris_ke)
    get_resep_df.clear()


# ================= Log_Transaksi =================

@st.cache_data(ttl=30, show_spinner=False)
def get_transaksi_df() -> pd.DataFrame:
    return _get_df(SHEET_TRANSAKSI)


def catat_transaksi(nama_karyawan: str, nama_jasa: str, metode_bayar: str, nama_pelanggan: str = "") -> dict:
    """
    Catat 1 transaksi jasa: harga diambil sebagai snapshot dari Master_Jasa saat ini,
    stok bahan dikurangi sesuai Resep_Jasa (stok boleh minus kalau kurang, dikoreksi
    lewat Stok_Opname). nama_pelanggan opsional, boleh dikosongkan.

    Pencegahan transaksi ganda TIDAK lagi dicek di sini (dulu lewat transaksi_duplikat()
    yang download seluruh Log_Transaksi tiap klik tombol Simpan -- boros API). Sekarang
    dicek di app.py pakai st.session_state (lokal, tanpa baca sheet sama sekali) SEBELUM
    fungsi ini dipanggil. Fungsi ini murni "simpan", tidak lagi merangkap validasi duplikat.
    """
    harga = _harga_jasa_fresh(nama_jasa)
    id_transaksi = f"TX-{now_wib().strftime('%Y%m%d%H%M%S%f')}"
    waktu = now_wib().strftime("%d-%m-%Y %H:%M:%S")

    ws = _get_ws(SHEET_TRANSAKSI)
    ws.append_row([id_transaksi, waktu, nama_karyawan, nama_jasa, harga, metode_bayar, nama_pelanggan])
    get_transaksi_df.clear()

    resep = get_resep_untuk_jasa(nama_jasa)
    for _, baris_resep in resep.iterrows():
        try:
            jumlah = float(baris_resep["Jumlah_Terpakai"])
        except (TypeError, ValueError):
            continue
        _ubah_stok_bahan(baris_resep["Nama_Bahan"], -jumlah)

    return {"berhasil": True, "pesan": f"Transaksi '{nama_jasa}' tersimpan.", "harga": harga}


def total_tunai_karyawan(nama_karyawan: str, tanggal: str) -> float:
    """tanggal format dd-mm-YYYY. Total transaksi Tunai milik karyawan pada tanggal itu.
    Pakai get_transaksi_df() (cached) bukan _get_df() langsung -- aman dari sisi
    keakuratan karena catat_transaksi() selalu memanggil get_transaksi_df.clear()
    tiap ada transaksi baru, jadi cache tidak pernah basi saat dipakai di sini."""
    df = get_transaksi_df()
    if df.empty:
        return 0
    df["_tgl"] = df["Waktu"].astype(str).str[:10]
    cocok = df[
        (df["Karyawan"] == nama_karyawan)
        & (df["_tgl"] == tanggal)
        & (df["Metode_Bayar"] == "Tunai")
    ]
    if cocok.empty:
        return 0
    return float(pd.to_numeric(cocok["Harga"], errors="coerce").fillna(0).sum())


# ================= Log_Pembelian_Bahan =================

@st.cache_data(ttl=30, show_spinner=False)
def get_pembelian_df() -> pd.DataFrame:
    return _get_df(SHEET_PEMBELIAN)


def catat_pembelian_bahan(nama_karyawan: str, nama_bahan: str, jumlah: float, total_harga: float):
    waktu = now_wib().strftime("%d-%m-%Y %H:%M:%S")
    ws = _get_ws(SHEET_PEMBELIAN)
    ws.append_row([waktu, nama_karyawan, nama_bahan, jumlah, total_harga])
    get_pembelian_df.clear()
    _ubah_stok_bahan(nama_bahan, jumlah)


# ================= Tutup_Kas =================

@st.cache_data(ttl=30, show_spinner=False)
def get_tutup_kas_df() -> pd.DataFrame:
    return _get_df(SHEET_TUTUP_KAS)


@st.cache_data(ttl=10, show_spinner=False)
def sudah_tutup_kas_hari_ini(nama_karyawan: str) -> bool:
    df = _get_df(SHEET_TUTUP_KAS)
    if df.empty:
        return False
    hari_ini = now_wib().strftime("%d-%m-%Y")
    cocok = df[(df["Karyawan"] == nama_karyawan) & (df["Tanggal"] == hari_ini)]
    return not cocok.empty


def catat_tutup_kas(nama_karyawan: str, total_fisik: float) -> dict:
    tanggal = now_wib().strftime("%d-%m-%Y")
    waktu = now_wib().strftime("%d-%m-%Y %H:%M:%S")
    total_sistem = total_tunai_karyawan(nama_karyawan, tanggal)
    selisih = total_fisik - total_sistem

    ws = _get_ws(SHEET_TUTUP_KAS)
    ws.append_row([waktu, nama_karyawan, tanggal, total_sistem, total_fisik, selisih])
    get_tutup_kas_df.clear()
    sudah_tutup_kas_hari_ini.clear()

    if selisih < 0:
        catat_utang_selisih(nama_karyawan, "Tutup_Kas", abs(selisih), f"Kekurangan kas tanggal {tanggal}")

    return {"total_sistem": total_sistem, "total_fisik": total_fisik, "selisih": selisih}


# ================= Stok_Opname =================

@st.cache_data(ttl=30, show_spinner=False)
def get_stok_opname_df() -> pd.DataFrame:
    return _get_df(SHEET_STOK_OPNAME)


def catat_stok_opname(nama_bahan: str, stok_fisik: float, keterangan: str = "") -> dict:
    stok_sistem = stok_bahan_sekarang(nama_bahan)
    selisih = stok_fisik - stok_sistem
    waktu = now_wib().strftime("%d-%m-%Y %H:%M:%S")

    ws = _get_ws(SHEET_STOK_OPNAME)
    ws.append_row([waktu, nama_bahan, stok_sistem, stok_fisik, selisih, keterangan])
    get_stok_opname_df.clear()

    # Koreksi Stok_Saat_Ini supaya sesuai hasil hitung fisik.
    _ubah_stok_bahan(nama_bahan, selisih)

    return {"stok_sistem": stok_sistem, "stok_fisik": stok_fisik, "selisih": selisih}


# ================= Utang_Selisih =================

@st.cache_data(ttl=30, show_spinner=False)
def get_utang_df() -> pd.DataFrame:
    return _get_df(SHEET_UTANG)


def catat_utang_selisih(nama_karyawan: str, sumber: str, jumlah: float, keterangan: str = ""):
    waktu = now_wib().strftime("%d-%m-%Y %H:%M:%S")
    ws = _get_ws(SHEET_UTANG)
    ws.append_row([waktu, nama_karyawan, sumber, jumlah, "Belum Lunas", keterangan])
    get_utang_df.clear()


def tandai_utang_lunas(waktu_baris: str, nama_karyawan: str):
    ws = _get_ws(SHEET_UTANG)
    df = _get_df(SHEET_UTANG)
    baris_ke = _cari_baris_ke(df, (df["Waktu"] == waktu_baris) & (df["Karyawan"] == nama_karyawan))
    if baris_ke is None:
        return
    ws.update_cell(baris_ke, _kolom_ke(SHEET_UTANG, "Status_Lunas"), "Lunas")
    get_utang_df.clear()


def rekap_pola_selisih() -> pd.DataFrame:
    """Total & jumlah kejadian selisih kas per karyawan, untuk dashboard owner."""
    df = get_utang_df()
    if df.empty:
        return df
    df = df.copy()
    df["Jumlah"] = pd.to_numeric(df["Jumlah"], errors="coerce").fillna(0)
    hasil = (
        df.groupby("Karyawan")["Jumlah"]
        .agg(["sum", "count"])
        .rename(columns={"sum": "Total_Selisih", "count": "Jumlah_Kejadian"})
        .reset_index()
    )
    return hasil