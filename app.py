import time

import pandas as pd
import streamlit as st

from utils import gdrive, gsheet, image_utils, security
from utils.format_utils import format_rupiah, format_tanggal_jam, now_wib

st.set_page_config(page_title="Sistem Barbershop ZZA", layout="centered")

gsheet.ensure_sheet_structure()

st.sidebar.title("Sistem Barbershop ZZA")
halaman = st.sidebar.radio("Menu", ["Halaman Karyawan", "Halaman Pemilik / Kasir"])


# ============================================================
# HALAMAN KARYAWAN
# ============================================================

def _form_login_pin(nama: str) -> bool:
    """Tampilkan captcha + PIN. Kembalikan True kalau sudah terverifikasi di sesi ini."""
    if st.session_state.get("pin_ok"):
        return True

    terkunci, pesan_lockout = gsheet.cek_lockout(nama)
    if terkunci:
        st.error(pesan_lockout)
        return False

    if "_captcha_soal" not in st.session_state:
        security.buat_captcha()

    st.write(f"Captcha: berapa hasil dari **{st.session_state['_captcha_soal']}** ?")
    jawaban_captcha = st.text_input("Jawaban captcha", key="captcha_input")
    pin = st.text_input("Masukkan PIN 6 digit", type="password", max_chars=6, key="pin_input")

    if st.button("Verifikasi PIN"):
        if not security.captcha_benar(jawaban_captcha):
            st.error("Jawaban captcha salah, coba lagi.")
            security.buat_captcha()
            return False

        if pin and gsheet.verifikasi_pin(nama, pin):
            gsheet.reset_pin_salah(nama)
            st.session_state["pin_ok"] = True
            security.buat_captcha()
            st.success("PIN benar.")
            st.rerun()
        else:
            hasil = gsheet.catat_pin_salah(nama)
            st.error(hasil["pesan"])
            security.buat_captcha()

    return st.session_state.get("pin_ok", False)


def _form_transaksi_jasa(nama: str, kas_sudah_ditutup: bool):
    st.subheader("Catat Transaksi Jasa")

    if kas_sudah_ditutup:
        st.info(
            "Kas hari ini sudah ditutup, jadi tidak bisa tambah transaksi baru. "
            "Kalau memang masih ada pelanggan setelah ini, hubungi pemilik untuk koreksi manual."
        )
        return

    df_jasa = gsheet.get_jasa_aktif()
    if df_jasa.empty:
        st.info("Belum ada Master_Jasa yang aktif. Minta pemilik menambahkan jasa dulu.")
        return

    nama_jasa = st.selectbox("Jasa", df_jasa["Nama_Jasa"].tolist(), key="pilih_jasa")
    harga = gsheet.harga_jasa(nama_jasa)
    st.write(f"Harga: **{format_rupiah(harga)}**")

    # Poin 3: peringatan stok kritis, tepat di bawah pilihan jasa. bahan_stok_menipis()
    # sudah di-cache (ttl 30 detik) jadi aman dipanggil di sini tiap rerun.
    df_menipis = gsheet.bahan_stok_menipis()
    if not df_menipis.empty:
        st.warning(f"⚠️ Stok menipis: {', '.join(df_menipis['Nama_Bahan'].tolist())}. Info ke pemilik untuk restock.")

    nama_pelanggan = st.text_input("Nama Pelanggan (opsional)", key="nama_pelanggan_transaksi")
    metode = st.radio("Metode Bayar", ["Tunai", "Non-tunai"], key="metode_bayar", horizontal=True)

    if st.button("Simpan Transaksi", key="btn_simpan_transaksi"):
        # Poin 2: cek transaksi ganda LOKAL via session_state, tidak baca sheet sama
        # sekali (dulu lewat gsheet.transaksi_duplikat() yang download seluruh
        # Log_Transaksi tiap klik -- sekarang dihapus dari gsheet.py).
        terakhir = st.session_state.get("_transaksi_terakhir")
        sekarang = time.time()
        adalah_duplikat = (
            terakhir is not None
            and terakhir["jasa"] == nama_jasa
            and terakhir["metode"] == metode
            and (sekarang - terakhir["waktu"]) <= gsheet.BATAS_DUPLIKAT_DETIK
        )
        if adalah_duplikat:
            st.warning("Transaksi yang sama baru saja tercatat. Kemungkinan double-klik, tidak disimpan lagi.")
        else:
            with st.spinner("Menyimpan transaksi..."):
                hasil = gsheet.catat_transaksi(nama, nama_jasa, metode, nama_pelanggan)
            if hasil["berhasil"]:
                st.session_state["_transaksi_terakhir"] = {
                    "jasa": nama_jasa, "metode": metode, "waktu": sekarang,
                }
                st.success(hasil["pesan"])
            else:
                st.warning(hasil["pesan"])


def _form_pembelian_bahan(nama: str):
    if not gsheet.boleh_restock(nama):
        return
    with st.expander("Catat Pembelian Bahan (Restock)"):
        df_bahan = gsheet.get_bahan_aktif()
        if df_bahan.empty:
            st.info("Belum ada Master_Bahan yang aktif.")
            return
        nama_bahan = st.selectbox("Bahan", df_bahan["Nama_Bahan"].tolist(), key="pilih_bahan_beli")
        jumlah = st.number_input("Jumlah dibeli", min_value=0.0, step=1.0, key="jumlah_beli")
        total_harga = st.number_input(
            "Total harga (Rp)", min_value=0, step=1000, format="%d", key="harga_beli"
        )
        if st.button("Simpan Pembelian Bahan"):
            if jumlah <= 0:
                st.warning("Jumlah harus lebih dari 0.")
            else:
                gsheet.catat_pembelian_bahan(nama, nama_bahan, jumlah, total_harga)
                st.success(f"Pembelian '{nama_bahan}' tersimpan, stok bertambah {jumlah}.")


def _form_tutup_kas(nama: str, wajib: bool):
    tanggal = now_wib().strftime("%d-%m-%Y")
    total_sistem = gsheet.total_tunai_karyawan(nama, tanggal)

    st.subheader("Tutup Kas")
    if wajib:
        st.warning("Tutup kas hari ini belum diisi. Absen Pulang baru bisa dilanjutkan setelah ini selesai.")
    st.write(f"Total transaksi Tunai tercatat sistem hari ini: **{format_rupiah(total_sistem)}**")

    total_fisik = st.number_input(
        "Jumlah uang tunai fisik yang dihitung", min_value=0, step=1000, format="%d", key="tutup_kas_fisik"
    )
    if st.button("Simpan Tutup Kas", key="btn_tutup_kas"):
        hasil = gsheet.catat_tutup_kas(nama, total_fisik)
        if hasil["selisih"] == 0:
            st.success("Tutup kas tersimpan. Kas pas, tidak ada selisih.")
        elif hasil["selisih"] > 0:
            st.info(f"Tutup kas tersimpan. Kas lebih {format_rupiah(hasil['selisih'])}.")
        else:
            st.warning(
                f"Tutup kas tersimpan. Kas kurang {format_rupiah(abs(hasil['selisih']))}. "
                "Selisih ini tercatat di Utang_Selisih."
            )
        st.rerun()


def _bagian_absen(nama: str, status_berikutnya: str):
    st.write(f"Absen berikutnya untuk **{nama}**: **{status_berikutnya}**")
    foto = st.camera_input("Ambil selfie untuk absen")

    if foto is not None:
        with st.spinner("Menyimpan absensi..."):
            watermark = format_tanggal_jam()
            foto_final = image_utils.kompres_dan_watermark(foto.getvalue(), watermark)

            folder_id = gdrive.get_folder_absensi_hari_ini()
            waktu_file = now_wib().strftime("%Y%m%d_%H%M%S")
            filename = f"{nama}_{status_berikutnya}_{waktu_file}.jpg"
            link_foto = gdrive.upload_foto(foto_final, filename, folder_id)

            gsheet.catat_absensi(nama, status_berikutnya, link_foto)

        st.success(f"Sukses! Absen {status_berikutnya} untuk {nama} tercatat.")
        st.session_state["pin_ok"] = False
        st.session_state["_siap_pulang"] = False


def halaman_karyawan():
    st.header("Presensi & Transaksi Karyawan")

    daftar_nama = gsheet.get_karyawan_aktif()
    if not daftar_nama:
        st.warning("Belum ada karyawan aktif di tab Data_Karyawan.")
        return

    nama = st.selectbox("Pilih nama Anda", daftar_nama, key="nama_karyawan")

    if st.session_state.get("_nama_terakhir") != nama:
        st.session_state["_nama_terakhir"] = nama
        st.session_state["pin_ok"] = False
        st.session_state["_siap_pulang"] = False
        security.buat_captcha()

    if not _form_login_pin(nama):
        return

    status_berikutnya = gsheet.status_absen_berikutnya(nama)
    if status_berikutnya is None:
        st.info(f"{nama} sudah tercatat Masuk & Pulang hari ini. Sampai jumpa besok!")
        return

    tutup_kas_selesai = gsheet.sudah_tutup_kas_hari_ini(nama)

    st.divider()
    _form_transaksi_jasa(nama, tutup_kas_selesai)
    _form_pembelian_bahan(nama)
    st.divider()

    if status_berikutnya == "Masuk":
        _bagian_absen(nama, status_berikutnya)
        return

    # status_berikutnya == "Pulang"
    if not tutup_kas_selesai:
        with st.expander("Tutup kas (boleh diisi kapan saja sebelum pulang)"):
            _form_tutup_kas(nama, wajib=False)

    if not st.session_state.get("_siap_pulang"):
        if st.button("Saya siap Absen Pulang"):
            st.session_state["_siap_pulang"] = True
            st.rerun()
        return

    if not tutup_kas_selesai:
        _form_tutup_kas(nama, wajib=True)
        return

    _bagian_absen(nama, status_berikutnya)


# ============================================================
# HALAMAN PEMILIK / KASIR
# ============================================================

def halaman_pemilik():
    st.header("Halaman Pemilik / Kasir")

    if not st.session_state.get("owner_ok"):
        password = st.text_input("Masukkan Password Master", type="password")
        if st.button("Masuk"):
            if password and password == st.secrets.get("MASTER_PASSWORD", ""):
                st.session_state["owner_ok"] = True
                st.rerun()
            else:
                st.error("Password salah.")
        return

    tab_keuangan, tab_master, tab_dashboard = st.tabs(
        ["Input Keuangan", "Master Data", "Dashboard Laporan"]
    )

    with tab_keuangan:
        _tab_input_keuangan()

    with tab_master:
        _tab_master_data()

    with tab_dashboard:
        _tab_dashboard()

    if st.button("Keluar"):
        st.session_state["owner_ok"] = False
        st.rerun()


def _tab_input_keuangan():
    with st.form("form_keuangan", clear_on_submit=True):
        tanggal = st.date_input("Tanggal", value=now_wib().date())
        jenis = st.selectbox("Jenis", ["Pemasukan", "Pengeluaran"])
        nominal = st.number_input("Nominal (Rp)", min_value=0, step=1000, format="%d")
        keterangan = st.text_input(
            "Keterangan (contoh: Omzet harian / Beli sampo / Token listrik)"
        )
        simpan = st.form_submit_button("Simpan")

    if simpan:
        if nominal <= 0:
            st.warning("Nominal harus lebih dari 0.")
        else:
            gsheet.catat_keuangan(tanggal.strftime("%d-%m-%Y"), jenis, nominal, keterangan)
            st.success(f"Tersimpan: {jenis} {format_rupiah(nominal)} - {keterangan}")


def _tab_master_data():
    sub_jasa, sub_bahan, sub_resep = st.tabs(["Jasa", "Bahan", "Resep Jasa"])

    with sub_jasa:
        st.subheader("Master Jasa")
        df_jasa = gsheet.get_master_jasa_df()
        if not df_jasa.empty:
            st.dataframe(df_jasa, width="stretch", hide_index=True)

        with st.form("form_tambah_jasa", clear_on_submit=True):
            nama_jasa = st.text_input("Nama Jasa")
            harga = st.number_input("Harga (Rp)", min_value=0, step=1000, format="%d")
            tambah = st.form_submit_button("Tambah Jasa")
        if tambah:
            if not nama_jasa:
                st.warning("Nama jasa tidak boleh kosong.")
            else:
                gsheet.tambah_jasa(nama_jasa, harga)
                st.success(f"Jasa '{nama_jasa}' ditambahkan.")
                st.rerun()

        if not df_jasa.empty:
            st.write("Ubah status jasa (nonaktifkan tanpa menghapus histori):")
            nama_pilih = st.selectbox("Pilih jasa", df_jasa["Nama_Jasa"].tolist(), key="ubah_status_jasa")
            status_baru = st.radio("Status baru", ["Aktif", "Nonaktif"], horizontal=True, key="status_jasa_baru")
            if st.button("Terapkan Status Jasa"):
                gsheet.ubah_status_jasa(nama_pilih, status_baru)
                st.success(f"Status '{nama_pilih}' diubah menjadi {status_baru}.")
                st.rerun()

    with sub_bahan:
        st.subheader("Master Bahan")
        df_bahan = gsheet.get_master_bahan_df()
        if not df_bahan.empty:
            st.dataframe(df_bahan, width="stretch", hide_index=True)

        with st.form("form_tambah_bahan", clear_on_submit=True):
            nama_bahan = st.text_input("Nama Bahan")
            satuan = st.text_input("Satuan (contoh: ml, gram, pcs)")
            stok_awal = st.number_input("Stok Awal", min_value=0.0, step=1.0)
            stok_minimum = st.number_input("Stok Minimum (untuk peringatan)", min_value=0.0, step=1.0)
            tambah_bahan = st.form_submit_button("Tambah Bahan")
        if tambah_bahan:
            if not nama_bahan or not satuan:
                st.warning("Nama bahan dan satuan tidak boleh kosong.")
            else:
                gsheet.tambah_bahan(nama_bahan, satuan, stok_awal, stok_minimum)
                st.success(f"Bahan '{nama_bahan}' ditambahkan.")
                st.rerun()

        if not df_bahan.empty:
            st.write("Ubah status bahan (nonaktifkan tanpa menghapus histori):")
            nama_pilih_bahan = st.selectbox(
                "Pilih bahan", df_bahan["Nama_Bahan"].tolist(), key="ubah_status_bahan"
            )
            status_baru_bahan = st.radio(
                "Status baru", ["Aktif", "Nonaktif"], horizontal=True, key="status_bahan_baru"
            )
            if st.button("Terapkan Status Bahan"):
                gsheet.ubah_status_bahan(nama_pilih_bahan, status_baru_bahan)
                st.success(f"Status '{nama_pilih_bahan}' diubah menjadi {status_baru_bahan}.")
                st.rerun()

    with sub_resep:
        st.subheader("Resep Jasa (Bahan yang Terpakai per Jasa)")
        df_resep = gsheet.get_resep_df()
        if not df_resep.empty:
            st.dataframe(df_resep, width="stretch", hide_index=True)
        else:
            st.info("Belum ada resep. Jasa tanpa resep dianggap tidak memakai bahan apa pun.")

        df_jasa_aktif = gsheet.get_jasa_aktif()
        df_bahan_aktif = gsheet.get_bahan_aktif()
        if df_jasa_aktif.empty or df_bahan_aktif.empty:
            st.info("Tambahkan minimal 1 Jasa aktif dan 1 Bahan aktif untuk membuat resep.")
        else:
            with st.form("form_tambah_resep", clear_on_submit=True):
                jasa_resep = st.selectbox("Jasa", df_jasa_aktif["Nama_Jasa"].tolist())
                bahan_resep = st.selectbox("Bahan", df_bahan_aktif["Nama_Bahan"].tolist())
                jumlah_resep = st.number_input("Jumlah terpakai per 1x jasa ini", min_value=0.0, step=0.1)
                tambah_resep_btn = st.form_submit_button("Tambah ke Resep")
            if tambah_resep_btn:
                if jumlah_resep <= 0:
                    st.warning("Jumlah harus lebih dari 0.")
                else:
                    gsheet.tambah_resep(jasa_resep, bahan_resep, jumlah_resep)
                    st.success(f"Resep '{jasa_resep}' + '{bahan_resep}' ditambahkan.")
                    st.rerun()


def _tab_dashboard():
    # Poin 1: tombol refresh manual. st.rerun() tidak menghapus login/cache -- cache
    # ttl=30 di gsheet.py tetap dihormati (kalau data belum lewat 30 detik, tetap
    # dari cache, bukan baca ulang API), ini murni memudahkan owner "tekan sekali
    # untuk lihat data terbaru" tanpa perlu klik menu lain dulu.
    if st.button("🔄 Segarkan Laporan"):
        st.rerun()

    st.subheader("Riwayat Absensi")
    df_absensi = gsheet.get_absensi_df()
    sedang_shift = gsheet.karyawan_sedang_shift()
    belum_tutup_kas = [nama for nama in sedang_shift if not gsheet.sudah_tutup_kas_hari_ini(nama)]
    if sedang_shift:
        st.write(f"Karyawan yang sedang shift (sudah Masuk, belum Pulang): {', '.join(sedang_shift)}")
    if belum_tutup_kas:
        st.warning(f"Pengingat: belum tutup kas hari ini -> {', '.join(belum_tutup_kas)}")
    with st.expander("Lihat tabel Riwayat Absensi"):
        if df_absensi.empty:
            st.info("Belum ada data absensi.")
        else:
            st.dataframe(df_absensi, width="stretch", hide_index=True)

    st.divider()
    st.subheader("Riwayat Keuangan")
    df_keuangan = gsheet.get_keuangan_df()
    if df_keuangan.empty:
        st.info("Belum ada data keuangan.")
    else:
        with st.expander("Lihat tabel Riwayat Keuangan"):
            df_tampil = df_keuangan.copy()
            df_tampil["Nominal"] = df_tampil["Nominal"].apply(format_rupiah)
            st.dataframe(df_tampil, width="stretch", hide_index=True)

        st.subheader("Grafik Pendapatan Harian (Keuangan)")
        df_pemasukan = df_keuangan[df_keuangan["Jenis"] == "Pemasukan"]
        if not df_pemasukan.empty:
            grafik = df_pemasukan.groupby("Tanggal")["Nominal"].sum()
            st.line_chart(grafik)

    st.divider()
    st.subheader("Riwayat Transaksi Jasa")
    df_transaksi = gsheet.get_transaksi_df()
    with st.expander("Lihat tabel Riwayat Transaksi Jasa"):
        if df_transaksi.empty:
            st.info("Belum ada transaksi jasa.")
        else:
            df_transaksi_tampil = df_transaksi.copy()
            df_transaksi_tampil["Harga"] = df_transaksi_tampil["Harga"].apply(format_rupiah)
            st.dataframe(df_transaksi_tampil, width="stretch", hide_index=True)

    st.divider()
    st.subheader("Rekap Kas per Karyawan (Tutup Kas)")
    df_kas = gsheet.get_tutup_kas_df()
    with st.expander("Lihat tabel Rekap Kas per Karyawan"):
        if df_kas.empty:
            st.info("Belum ada data tutup kas.")
        else:
            df_kas_tampil = df_kas.copy()
            for kolom in ["Total_Tunai_Sistem", "Total_Tunai_Fisik", "Selisih"]:
                df_kas_tampil[kolom] = df_kas_tampil[kolom].apply(format_rupiah)
            st.dataframe(df_kas_tampil, width="stretch", hide_index=True)

    st.subheader("Rekap Non-Tunai per Karyawan")
    with st.expander("Lihat tabel Rekap Non-Tunai"):
        if not df_transaksi.empty:
            df_non_tunai = df_transaksi[df_transaksi["Metode_Bayar"] == "Non-tunai"].copy()
            if df_non_tunai.empty:
                st.info("Belum ada transaksi non-tunai.")
            else:
                df_non_tunai["_tgl"] = df_non_tunai["Waktu"].astype(str).str[:10]
                df_non_tunai["Harga"] = pd.to_numeric(df_non_tunai["Harga"], errors="coerce").fillna(0)
                rekap_non_tunai = df_non_tunai.groupby(["Karyawan", "_tgl"])["Harga"].sum().reset_index()
                rekap_non_tunai = rekap_non_tunai.rename(columns={"_tgl": "Tanggal"})
                rekap_non_tunai["Harga"] = rekap_non_tunai["Harga"].apply(format_rupiah)
                st.dataframe(rekap_non_tunai, width="stretch", hide_index=True)
        else:
            st.info("Belum ada transaksi non-tunai.")

    st.divider()
    st.subheader("Status Stok Bahan")
    df_bahan_semua = gsheet.get_master_bahan_df()
    df_menipis = gsheet.bahan_stok_menipis()
    if not df_bahan_semua.empty and not df_menipis.empty:
        st.warning(f"Stok menipis: {', '.join(df_menipis['Nama_Bahan'].tolist())}")
    with st.expander("Lihat tabel Status Stok Bahan"):
        if df_bahan_semua.empty:
            st.info("Belum ada Master_Bahan.")
        else:
            st.dataframe(df_bahan_semua, width="stretch", hide_index=True)

    st.subheader("Stok Opname (Koreksi Stok Fisik)")
    df_bahan_aktif = gsheet.get_bahan_aktif()
    if df_bahan_aktif.empty:
        st.info("Belum ada bahan aktif untuk di-opname.")
    else:
        with st.form("form_stok_opname", clear_on_submit=True):
            bahan_opname = st.selectbox("Bahan", df_bahan_aktif["Nama_Bahan"].tolist())
            stok_fisik = st.number_input("Stok fisik hasil hitung", min_value=0.0, step=1.0)
            keterangan_opname = st.text_input("Keterangan (opsional)")
            simpan_opname = st.form_submit_button("Simpan Stok Opname")
        if simpan_opname:
            hasil_opname = gsheet.catat_stok_opname(bahan_opname, stok_fisik, keterangan_opname)
            st.success(
                f"Stok Opname '{bahan_opname}' tersimpan. Selisih: {hasil_opname['selisih']}. "
                "Stok sistem sudah dikoreksi."
            )
            st.rerun()

    st.divider()
    st.subheader("Riwayat Pola Selisih per Karyawan")
    df_pola = gsheet.rekap_pola_selisih()
    with st.expander("Lihat tabel Pola Selisih"):
        if df_pola is None or df_pola.empty:
            st.info("Belum ada data selisih.")
        else:
            df_pola_tampil = df_pola.copy()
            df_pola_tampil["Total_Selisih"] = df_pola_tampil["Total_Selisih"].apply(format_rupiah)
            st.dataframe(df_pola_tampil, width="stretch", hide_index=True)

    st.subheader("Utang Selisih (Belum Lunas)")
    df_utang = gsheet.get_utang_df()
    if df_utang.empty:
        st.info("Belum ada data utang selisih.")
    else:
        df_belum_lunas = df_utang[df_utang["Status_Lunas"] == "Belum Lunas"]
        if df_belum_lunas.empty:
            st.info("Semua utang selisih sudah lunas.")
        else:
            with st.expander("Lihat tabel Utang Selisih Belum Lunas", expanded=True):
                df_belum_lunas_tampil = df_belum_lunas.copy()
                df_belum_lunas_tampil["Jumlah"] = df_belum_lunas_tampil["Jumlah"].apply(format_rupiah)
                st.dataframe(df_belum_lunas_tampil, width="stretch", hide_index=True)

            pilihan = [f"{row['Waktu']} | {row['Karyawan']}" for _, row in df_belum_lunas.iterrows()]
            baris_pilih = st.selectbox("Tandai lunas (Waktu | Karyawan)", pilihan, key="pilih_lunas")
            if st.button("Tandai Lunas"):
                waktu_terpilih, nama_terpilih = [bagian.strip() for bagian in baris_pilih.split("|", 1)]
                gsheet.tandai_utang_lunas(waktu_terpilih, nama_terpilih)
                st.success("Ditandai lunas.")
                st.rerun()


if halaman == "Halaman Karyawan":
    halaman_karyawan()
else:
    halaman_pemilik()