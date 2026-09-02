"""
Utilitas: format Rupiah, nama bulan berbahasa Indonesia, dan waktu zona WIB.
"""
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")

NAMA_BULAN = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
    9: "September", 10: "Oktober", 11: "November", 12: "Desember",
}


def now_wib() -> datetime:
    """Waktu saat ini di zona WIB (Asia/Jakarta)."""
    return datetime.now(WIB)


def format_tanggal_jam(dt: Optional[datetime] = None) -> str:
    """Format 'dd-mm-YYYY HH:MM WIB', dipakai untuk watermark foto."""
    if dt is None:
        dt = now_wib()
    return dt.strftime("%d-%m-%Y %H:%M") + " WIB"


def format_rupiah(nominal) -> str:
    """
    Format angka menjadi string Rupiah, contoh: 1500000 -> 'Rp 1.500.000'
    Aman untuk input int, float, string angka, atau nilai kosong.
    """
    try:
        angka = int(round(float(nominal)))
    except (TypeError, ValueError):
        return "Rp 0"
    minus = "-" if angka < 0 else ""
    angka = abs(angka)
    teks = f"{angka:,}".replace(",", ".")
    return f"{minus}Rp {teks}"


def nama_folder_bulan(dt: Optional[datetime] = None) -> str:
    """Contoh output: '08_Agustus' (dipakai untuk struktur folder Google Drive)."""
    if dt is None:
        dt = now_wib()
    return f"{dt.month:02d}_{NAMA_BULAN[dt.month]}"