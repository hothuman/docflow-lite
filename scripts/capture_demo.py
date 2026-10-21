"""Capture the actual offscreen Qt application and its real generation result."""
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PIL import Image, ImageDraw, ImageFont
from docflow.batch import prepare
from docflow.cli import demo_profile
from docflow.gui import MainWindow
from docflow.profile import Profile
from docflow.validation import values_for

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "site" / "dist" / "assets"
FRAMES = ROOT.parent / "qa" / "video-frames"


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    FRAMES.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1440, 940)
    window.show()
    window.load_demo()
    window.data_path.setText("Встроенный пример / clients.xlsx")
    window.output_path.setText("docflow-output")
    app.processEvents()
    captures = []
    def capture(number, title, subtitle):
        app.processEvents()
        raw = FRAMES / f"app-{number}.png"
        window.grab().save(str(raw))
        if number == 0:
            window.grab().save(str(ASSETS / "app.png"))
        canvas = Image.new("RGB", (1600, 1080), "#f8f8f3")
        draw = ImageDraw.Draw(canvas)
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        draw.text((50, 26), title, fill="#142b3a", font=ImageFont.truetype(font, 34))
        draw.text((50, 79), subtitle, fill="#5b6c76", font=ImageFont.truetype(font, 20))
        screenshot = Image.open(raw).convert("RGB")
        screenshot.thumbnail((1500, 905))
        canvas.paste(screenshot, ((1600-screenshot.width)//2, 135))
        draw.text((50, 1042), "DocFlow Lite 0.1.1  ·  Реальный интерфейс  ·  Вымышленные данные", fill="#5b6c76", font=ImageFont.truetype(font, 16))
        frame = FRAMES / f"frame-{number}.png"
        canvas.save(frame)
        captures.append(frame)
    capture(0, "Из Excel — в комплект документов Word", "Встроенный пример: 3 записи, 2 DOCX-шаблона")
    window.tabs.setCurrentIndex(1)
    capture(1, "Сначала проверьте подстановку", "Текстовый просмотр. Оформление итогового документа проверяется в Word")
    window.row_selector.setCurrentIndex(2)
    capture(2, "Ошибки видны до отправки документов", "В третьей записи пропущена услуга и указана отрицательная сумма")
    window.start_generation()
    deadline = time.monotonic() + 30
    while (window.worker.isRunning() or window.last_result is None) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    window.worker.wait(1000)
    app.processEvents()
    assert window.last_result and window.last_result.documents == 4
    window.tabs.setCurrentIndex(0)
    capture(3, "Готово: 4 DOCX и отчёт о пропущенной записи", "2 записи обработаны. 1 запись требует исправления. Исходные файлы не изменены")
    prepared = prepare(Profile.load(demo_profile()))
    rows = []
    for record in prepared.table.records:
        values, issues = values_for(record, prepared.profile.mapping, prepared.profile.rules)
        rows.append({"number":record.values["Номер"],"client":record.values["Клиент"],"service":record.values["Услуга"],"documents":0 if issues else len(prepared.templates),"errors":[f"{i.field}: {i.message}" for i in issues],"previews":[] if issues else [t.preview(values) for t in prepared.templates]})
    payload = json.dumps(rows, ensure_ascii=False, indent=2).replace("<", "\\u003c").replace(">", "\\u003e")
    (ASSETS / "demo-data.js").write_text("window.DOCFLOW_DEMO = " + payload + ";\n", encoding="utf-8")
    (FRAMES / "frames.txt").write_text("".join(f"file '{frame.as_posix()}'\nduration 6\n" for frame in captures) + f"file '{captures[-1].as_posix()}'\n", encoding="utf-8")
    (ROOT.parent / "qa" / "capture-result.json").write_text(json.dumps({"documents":window.last_result.documents,"accepted":window.last_result.accepted,"rejected":window.last_result.rejected},indent=2),encoding="utf-8")
    window.close()
    print(json.dumps({"frames":len(captures),"screenshot":str(ASSETS / "app.png"),"documents":4}))


if __name__ == "__main__":
    main()

