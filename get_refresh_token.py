"""
JALANKAN SEKALI SAJA DI KOMPUTER LOKAL (bukan di Streamlit Cloud).

Tujuan: login pakai akun Gmail pribadimu, lalu dapatkan refresh_token
yang nanti dipakai app Streamlit supaya foto absensi tersimpan di
KUOTA GMAIL-MU SENDIRI (bukan kuota service account yang 0 GB).

Cara pakai:
1. pip install google-auth-oauthlib
2. Simpan file JSON hasil download "OAuth client ID (Desktop app)"
   dari Google Cloud Console, beri nama: client_secret.json
   (satu folder dengan script ini)
3. Jalankan: python get_refresh_token.py
4. Browser akan terbuka -> login dengan akun Gmail yang ingin dipakai
   sebagai "pemilik" folder & foto -> klik Allow.
5. Salin nilai client_id, client_secret, refresh_token yang tercetak
   ke st.secrets (lihat instruksi di bawah).
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0)

print("\n=== SALIN INI KE st.secrets (secrets.toml atau Streamlit Cloud) ===\n")
print("[gdrive_oauth]")
print(f'client_id = "{creds.client_id}"')
print(f'client_secret = "{creds.client_secret}"')
print(f'refresh_token = "{creds.refresh_token}"')