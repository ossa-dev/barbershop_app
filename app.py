import streamlit as st

from utils import gdrive, gsheet, image_utils
from utils.format_utils import format_rupiah, format_tanggal_jam, now_wib

st.set_page_config(page_title="Sistem Barbershop ZZA", page_icon="💈", layout="centered")

gsheet.ensure_sheet_structure()

st.sidebar.title("💈 Sistem Barbershop ZZA")
halaman = st.sidebar.radio("Menu", ["Halaman Karyawan", "Halaman Pemilik / Kasir"])


def halaman_karyawan():
    st.header("📋 Presensi Karyawan")

    daftar_nama = gsheet.get_karyawan_aktif()
    if not daftar_nama:
        st.warning("Belum ada karyawan aktif di tab Data_Karyawan.")
        return

    nama = st.selectbox("Pilih nama Anda", daftar_nama, key="nama_karyawan")

    # Reset status verifikasi PIN kalau karyawan yang dipilih berganti
    if st.session_state.get("_nama_terakhir") != nama:
        st.session_state["_nama_terakhir"] = nama
        st.session_state["pin_ok"] = False

    pin = st.text_input("Masukkan PIN 4 digit", type="password", max_chars=4, key="pin_input")

    if st.button("Verifikasi PIN"):
        if pin and gsheet.verifikasi_pin(nama, pin):
            st.session_state["pin_ok"] = True
            st.success("PIN benar. Silakan ambil foto selfie di bawah.")
        else:
            st.session_state["pin_ok"] = False
            st.error("PIN salah. Kamera tidak akan muncul sampai PIN benar.")

    if not st.session_state.get("pin_ok"):
        return

    status_berikutnya = gsheet.status_absen_berikutnya(nama)
    if status_berikutnya is None:
        st.info(f"{nama} sudah tercatat Masuk & Pulang hari ini. Sampai jumpa besok!")
        return

    st.write(f"Absen berikutnya untuk **{nama}**: **{status_berikutnya}**")
    foto = st.camera_input("Ambil selfie untuk absen")

    if foto is not None:
        with st.spinner("Menyimpan absensi..."):
            watermark = format_tanggal_jam()
            foto_final = image_utils.kompres_dan_watermark(foto.getvalue(), watermark)

            folder_id = gdrive.get_folder_absensi_bulan_ini()
            waktu_file = now_wib().strftime("%Y%m%d_%H%M%S")
            filename = f"{nama}_{status_berikutnya}_{waktu_file}.jpg"
            link_foto = gdrive.upload_foto(foto_final, filename, folder_id)

            gsheet.catat_absensi(nama, status_berikutnya, link_foto)

        st.success(f"Sukses! Absen {status_berikutnya} untuk {nama} tercatat.")
        st.session_state["pin_ok"] = False


def halaman_pemilik():
    st.header("🔐 Halaman Pemilik / Kasir")

    if not st.session_state.get("owner_ok"):
        password = st.text_input("Masukkan Password Master", type="password")
        if st.button("Masuk"):
            if password and password == st.secrets.get("MASTER_PASSWORD", ""):
                st.session_state["owner_ok"] = True
                st.rerun()
            else:
                st.error("Password salah.")
        return

    tab_input, tab_dashboard = st.tabs(["💰 Input Keuangan", "📊 Dashboard Laporan"])

    with tab_input:
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

    with tab_dashboard:
        st.subheader("Riwayat Absensi")
        df_absensi = gsheet.get_absensi_df()
        if df_absensi.empty:
            st.info("Belum ada data absensi.")
        else:
            st.dataframe(df_absensi, use_container_width=True, hide_index=True)

        st.subheader("Riwayat Keuangan")
        df_keuangan = gsheet.get_keuangan_df()
        if df_keuangan.empty:
            st.info("Belum ada data keuangan.")
        else:
            df_tampil = df_keuangan.copy()
            df_tampil["Nominal"] = df_tampil["Nominal"].apply(format_rupiah)
            st.dataframe(df_tampil, use_container_width=True, hide_index=True)

            st.subheader("Grafik Pendapatan Harian")
            df_pemasukan = df_keuangan[df_keuangan["Jenis"] == "Pemasukan"]
            if not df_pemasukan.empty:
                grafik = df_pemasukan.groupby("Tanggal")["Nominal"].sum()
                st.line_chart(grafik)
            else:
                st.info("Belum ada data Pemasukan untuk digrafikkan.")

    if st.button("Keluar"):
        st.session_state["owner_ok"] = False
        st.rerun()


if halaman == "Halaman Karyawan":
    halaman_karyawan()
else:
    halaman_pemilik()
