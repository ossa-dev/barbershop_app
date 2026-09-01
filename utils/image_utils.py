"""
Kompresi foto absensi + watermark tanggal & jam.
Hasil disimpan sebagai JPEG (format yang langsung bisa dipreview di Google Drive).
"""
import io

from PIL import Image, ImageDraw, ImageFont

MAX_LEBAR = 640        # px, foto di-resize agar tidak terlalu besar tapi tetap jelas
JPEG_QUALITY = 55      # 0-100, dikompresi agresif untuk hemat penyimpanan Drive


def _load_font(ukuran: int):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", ukuran)
    except Exception:
        try:
            return ImageFont.load_default(size=ukuran)
        except TypeError:
            return ImageFont.load_default()


def kompres_dan_watermark(foto_bytes: bytes, teks_watermark: str) -> bytes:
    """
    - Resize agar lebar maksimum MAX_LEBAR px (tetap proporsional, tidak gepeng).
    - Cetak teks_watermark (tanggal & jam) di pojok kanan bawah dengan kotak semi-transparan
      agar tetap terbaca di foto terang maupun gelap.
    - Simpan sebagai JPEG terkompresi.
    """
    img = Image.open(io.BytesIO(foto_bytes)).convert("RGB")

    if img.width > MAX_LEBAR:
        rasio = MAX_LEBAR / img.width
        img = img.resize((MAX_LEBAR, int(img.height * rasio)), Image.LANCZOS)

    draw = ImageDraw.Draw(img, "RGBA")
    ukuran_font = max(16, img.width // 28)
    font = _load_font(ukuran_font)

    bbox = draw.textbbox((0, 0), teks_watermark, font=font)
    teks_w, teks_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    padding = 10
    x2, y2 = img.width - padding, img.height - padding
    x1, y1 = x2 - teks_w - (padding * 2), y2 - teks_h - (padding * 2)

    draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0, 140))
    draw.text((x1 + padding, y1 + padding), teks_watermark, font=font, fill=(255, 255, 255, 255))

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue()