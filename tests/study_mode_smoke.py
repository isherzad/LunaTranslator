"""Headless Windows smoke test for integrated Japanese Study Mode."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1] / "src" / "LunaTranslator"
sys.path.insert(0,str(ROOT))

from qtsymbols import QApplication
from gui import study_mode

def run():
    app = QApplication.instance() or QApplication([])
    assert study_mode.kata_to_hira("アシタ") == "あした"
    assert study_mode.kana_to_romaji("あした") == "ashita"
    assert study_mode.kana_to_romaji("きょう") == "kyou"
    class Word:
        word = "学校"
        kana = "ガッコウ"
        prototype = "学校"
        wordclass = "名詞"
    class Parser:
        def safeparse(self,text):
            return [Word()] if text == "学校" else []
    tokens = study_mode.segment("学校", Parser())
    assert [t.surface for t in tokens] == ["学校"]
    assert tokens[0].ruby == "がっこう"
    with tempfile.TemporaryDirectory() as tmp:
        study_mode.USER_DIR = Path(tmp)
        with sqlite3.connect(str(study_mode.USER_DIR / "jmdict.sqlite3")) as conn:
            conn.execute("CREATE TABLE dictionary (term TEXT, reading TEXT, pos TEXT, meanings TEXT, priority INTEGER)")
            conn.execute("INSERT INTO dictionary VALUES (?,?,?,?,?)", ("学校","がっこう","noun","school",0))
        lookup = study_mode.JMdict()
        assert lookup.lookup(tokens[0])["meaning"] == "school"
        view = study_mode.StudyMode(None)
        view.parser_tried = True
        view.parser = Parser()
        view.set_english("I went to school.")
        view.set_japanese("学校")
        assert len(view.canvas.hitboxes) == 1, view.canvas.hitboxes
        assert view.english == "I went to school."
        view.options.values["hide_english"] = True
        view.canvas.relayout()
        view.canvas.grab()
        view.pin(tokens[0])
        assert len(view.pinned) == 1
        view.pinned[0].close()
        view.options.save()
        assert (Path(tmp) / "study_mode.json").exists()
        view.close()
        view.dictionary.close()
        lookup.close()
        app.processEvents()
    print("Study Mode GUI + dictionary smoke test passed")
    return 0

if __name__ == "__main__":
    sys.exit(run())
