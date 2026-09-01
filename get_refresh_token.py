from google_auth_oauthlib.flow import InstalledAppFlow

# Harus sama persis dengan SCOPES di utils/gdrive.py, kalau tidak sama
# refresh token yang dihasilkan akan ditolak Google (invalid_scope).
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0)

print("\n=== SALIN INI KE st.secrets (secrets.toml atau Streamlit Cloud) ===\n")
print("[gdrive_oauth]")
print(f'client_id = "{creds.client_id}"')
print(f'client_secret = "{creds.client_secret}"')
print(f'refresh_token = "{creds.refresh_token}"')