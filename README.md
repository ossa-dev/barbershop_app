
Salin seluruh teks di bawah ini dan simpan ke dalam file **`README.md`** di folder utama proyek Anda.

```markdown
# Aplikasi Presensi & Pencatatan Keuangan Sederhana

Aplikasi presensi karyawan (dengan foto *selfie* dan *watermark*) serta pencatatan keuangan bisnis. Sistem ini dibangun menggunakan Streamlit, Google Sheets, dan Google Drive tanpa memerlukan *database* berbayar, beroperasi sepenuhnya dalam ekosistem Google gratis.

## 1. Struktur Proyek

```text
project_root/
├── app.py                        # Aplikasi utama (Halaman Karyawan & Pemilik)
├── requirements.txt              # Daftar library Python
├── .streamlit/
│   └── secrets.toml.example      # Template kredensial (JANGAN gunakan file ini langsung)
└── utils/
    ├── gsheet.py                 # Modul koneksi ke Google Sheets
    ├── gdrive.py                 # Modul koneksi ke Google Drive
    ├── image_utils.py            # Pemrosesan kompresi foto & watermark
    └── format_utils.py           # Pemformatan zona waktu & nominal mata uang

```

## 2. Setup Database (Google Sheets)

1. Buat satu Google Spreadsheet baru menggunakan akun Gmail operasional bisnis Anda.
2. Buka file JSON kredensial *Service Account*, lalu salin alamat email pada bagian `client_email` (berakhiran `@...iam.gserviceaccount.com`).
3. Klik tombol **Share** (Bagikan) pada Spreadsheet tersebut, tambahkan alamat email *Service Account*, dan setel hak akses sebagai **Editor**.
4. Salin **Spreadsheet ID** yang terdapat di dalam URL:
   `https://docs.google.com/spreadsheets/d/SALIN_ID_INI_SAJA/edit`
5. Anda **tidak perlu** membuat kolom manual. Saat dijalankan pertama kali, aplikasi otomatis membuat tiga tab:

* **Data_Karyawan:** Nama, PIN, Status
* **Log_Absensi:** Waktu, Nama, Status, Link Foto Drive
* **Keuangan:** Tanggal, Jenis, Nominal, Keterangan

6. Isi tab `Data_Karyawan` secara manual sebagai data awal pengenalan sistem:

| Nama | PIN  | Status |
| ---- | ---- | ------ |
| Budi | 1234 | Aktif  |
| Andi | 5678 | Resign |

## 3. Konfigurasi Keamanan (Streamlit Cloud)

Kredensial akses (file JSON) **tidak boleh** diunggah ke repositori publik.

1. Buka *dashboard* **Streamlit Cloud → App Anda → Settings → Secrets**.
2. Salin isi format dasar dari `.streamlit/secrets.toml.example` ke dalam kotak teks yang tersedia.
3. Ganti nilainya dengan data spesifik Anda:

* `SPREADSHEET_ID`: ID dari langkah kedua.
* `MASTER_PASSWORD`: Kata sandi rahasia untuk mengakses modul Pemilik/Kasir.
* `[gcp_service_account]`: Salin seluruh blok teks dari file JSON asli (pastikan karakter `\n` pada baris `private_key` tetap utuh).

*Catatan:* Untuk proses pengujian lokal di komputer, simpan konfigurasi yang sama ke dalam file bernama `.streamlit/secrets.toml`.

## 4. Proses Deploy ke Cloud

1. Buat akun GitHub menggunakan email bisnis Anda dan buat repositori baru dengan visibilitas **Private**.
2. Unggah seluruh direktori proyek, **kecuali** file `.streamlit/secrets.toml` yang berisi kredensial asli. File `.example` aman untuk disertakan.
3. Tautkan akun GitHub ke Streamlit Cloud dan pilih repositori tersebut.
4. Klik *Deploy*, lalu segera amankan aplikasi dengan memasukkan kredensial rahasia ke menu *Secrets* sesuai langkah sebelumnya.

## 5. Panduan Penggunaan Fitur

**Halaman Karyawan (Presensi Kehadiran):**

* Karyawan memilih nama melalui *dropdown* (hanya menampilkan personel berstatus "Aktif").
* Karyawan memasukkan PIN rahasia 4 digit untuk memvalidasi akses kamera.
* Sistem mendeteksi arah status presensi secara otomatis ("Masuk" atau "Pulang") berdasarkan riwayat pada hari tersebut.
* Aplikasi mengambil foto, menempelkan *watermark* jam/tanggal aktual, mengompresi data, dan mengunggahnya ke hierarki folder Google Drive (`Folder_Utama/Absensi/<tahun>/<bulan>/`).
* Tautan akses foto tercatat otomatis pada Google Sheets.

**Halaman Pemilik/Kasir:**

* Dilindungi oleh otentikasi `MASTER_PASSWORD`.
* **Tab Input Keuangan:** Antarmuka untuk mencatat arus kas (pemasukan dan pengeluaran).
* **Tab Dashboard:** Menampilkan tabel agregasi riwayat presensi, pembukuan kas, serta visualisasi grafik pendapatan harian.

## 6. Standar Keamanan Aplikasi

* Penempatan kode dilindungi visibilitas repositori privat.
* Integrasi *Service Account* dikelola secara eksklusif menggunakan sistem variabel lingkungan (Streamlit Secrets).
* Modul dasbor admin diamankan menggunakan enkripsi *password* khusus pemegang otoritas data.

## 7. Mitigasi Limitasi Kuota Google Drive

*Service Account* memiliki batasan kuota penyimpanan independen. Jika Anda mengalami kegagalan unggah foto (*storage quota exceeded*), gunakan solusi *bypass* berikut:

* Buat folder markas (contoh: `Sistem_Presensi_App`) secara manual melalui Google Drive utama Anda.
* Bagikan folder tersebut ke `client_email` dari akun robot Anda dengan wewenang **Editor**.
* Sistem dirancang untuk mencari nama folder presisi secara otomatis dan "menumpang" pengunggahan menggunakan batas penyimpanan akun Gmail utama (gratis 15GB).

## 8. Optimasi Penyimpanan Media

Seluruh foto *selfie* kehadiran akan dikonversi menjadi format **JPEG** dengan pembatasan resolusi lebar maksimal 1080px dan kompresi rasio kualitas 80%. Konfigurasi ini memaksa ukuran fail tetap ringan demi menghemat ruang penyimpanan, tanpa mengurangi kejernihan identifikasi visual.

```

```
