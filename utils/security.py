"""
Utilitas keamanan sederhana: captcha matematika untuk halaman login karyawan.
Tidak butuh API eksternal, cukup untuk menahan bot/script sederhana yang
mencoba menebak PIN secara otomatis.
"""
import random

import streamlit as st


def buat_captcha():
    """Buat soal captcha baru dan simpan jawabannya di session_state."""
    a = random.randint(1, 9)
    b = random.randint(1, 9)
    st.session_state["_captcha_soal"] = f"{a} + {b}"
    st.session_state["_captcha_jawaban"] = a + b


def captcha_benar(jawaban_input) -> bool:
    jawaban_asli = st.session_state.get("_captcha_jawaban")
    if jawaban_asli is None:
        return False
    try:
        return int(jawaban_input) == int(jawaban_asli)
    except (TypeError, ValueError):
        return False