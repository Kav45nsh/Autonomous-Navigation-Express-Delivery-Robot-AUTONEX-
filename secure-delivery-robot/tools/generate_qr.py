"""
Generate printable marker QR codes from settings.QR_COMMAND_MAP.

    python tools/generate_qr.py --size 12

Print at 10 cm across or larger. Small codes are the number one reason
detection "doesn't work". Error correction is set to H so a scuffed or
partially obscured code still reads. This makes one PNG per entry in
QR_COMMAND_MAP: MARKER 1..5 and STOP.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import qrcode
from PIL import Image, ImageDraw, ImageFont

from config import settings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=10)
    a = ap.parse_args()

    for payload, command in settings.QR_COMMAND_MAP.items():
        qr = qrcode.QRCode(box_size=a.size, border=4,
                           error_correction=qrcode.constants.ERROR_CORRECT_H)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        canvas = Image.new("RGB", (img.width, img.height + 70), "white")
        canvas.paste(img, (0, 0))
        d = ImageDraw.Draw(canvas)
        try:
            f1 = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
            f2 = ImageFont.truetype("DejaVuSans.ttf", 18)
        except OSError:
            f1 = f2 = ImageFont.load_default()
        for text, font, dy in ((payload, f1, 8),
                               (f"-> {command}", f2, 40)):
            w = d.textlength(text, font=font)
            d.text(((canvas.width - w) / 2, img.height + dy), text, "black", font=font)

        safe_name = payload.replace(" ", "_")
        out = settings.QR_CODES_DIR / f"{safe_name}.png"
        canvas.save(out)
        print(f"  {out.name}  ({payload} -> {command})")

    print(f"\n{len(settings.QR_COMMAND_MAP)} codes in {settings.QR_CODES_DIR}")


if __name__ == "__main__":
    main()
