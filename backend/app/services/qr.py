"""QR code generation for assets (Python `qrcode` library)."""
import base64
import io
import uuid

import qrcode
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Asset


def new_qr_code(db: Session) -> str:
    while True:
        code = f"FF-{uuid.uuid4().hex[:10].upper()}"
        if not db.scalar(select(Asset.asset_id).where(Asset.qr_code == code)):
            return code


def scan_url(code: str) -> str:
    """The QR encodes a link to the report form, so any phone camera opens it pre-filled."""
    return f"{settings.FRONTEND_URL}/report?qr={code}"


def qr_png_bytes(code: str) -> bytes:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(scan_url(code))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue()


def qr_data_uri(code: str) -> str:
    return "data:image/png;base64," + base64.b64encode(qr_png_bytes(code)).decode("ascii")
