"""Optional in-process English -> Japanese study view for LunaTranslator.
Uses LunaTranslator's existing translation events and its configured MeCab.
No separate overlay, WebSocket, or translation API required.
"""
from __future__ import annotations
import json
import re
import sqlite3
from pathlib import Path
from qtsymbols import *

USER_DIR = Path(__file__).resolve().parents[2] / "userconfig"
KANJI = re.compile(r"[\u3400-\u9fff\u3005]")
JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
DEFAULTS = {
    "english_size": 18, "japanese_size": 23, "furigana_size": 12,
    "section_gap": 17, "line_gap": 12, "padding": 18, "opacity": 95,
    "show_english": True, "show_japanese": True, "hide_english": False,
    "hover_romaji": True, "selectable_text": True,
    "shift_hover_dictionary": True,
}

def kata_to_hira(text):
    return "".join(chr(ord(c) - 96) if "ァ" <= c <= "ヶ" else c for c in text)

BASE = (
    ("あいうえお", "a i u e o"), ("かきくけこ", "ka ki ku ke ko"),
    ("さしすせそ", "sa shi su se so"), ("たちつてと", "ta chi tsu te to"),
    ("なにぬねの", "na ni nu ne no"), ("はひふへほ", "ha hi fu he ho"),
    ("まみむめも", "ma mi mu me mo"), ("やゆよ", "ya yu yo"),
    ("らりるれろ", "ra ri ru re ro"), ("わをん", "wa o n"),
    ("がぎぐげご", "ga gi gu ge go"), ("ざじずぜぞ", "za ji zu ze zo"),
    ("だぢづでど", "da ji zu de do"), ("ばびぶべぼ", "ba bi bu be bo"),
    ("ぱぴぷぺぽ", "pa pi pu pe po"), ("ぁぃぅぇぉ", "a i u e o")
)
ROMA = {k: v for kana, rom in BASE for k, v in zip(kana, rom.split())}
for k, prefix in (("き","ky"),("し","sh"),("ち","ch"),("に","ny"),
                  ("ひ","hy"),("み","my"),("り","ry"),("ぎ","gy"),
                  ("じ","j"),("び","by"),("ぴ","py")):
    for suffix, vowel in (("ゃ","a"),("ゅ","u"),("ょ","o")):
        ROMA[k + suffix] = prefix + vowel
ROMA.update({"しゃ":"sha","しゅ":"shu","しょ":"sho","ちゃ":"cha",
             "ちゅ":"chu","ちょ":"cho","じゃ":"ja","じゅ":"ju",
             "じょ":"jo","ふぁ":"fa","ふぃ":"fi","ふぇ":"fe",
             "ふぉ":"fo","てぃ":"ti","でぃ":"di","うぃ":"wi",
             "うぇ":"we","うぉ":"wo"})

def kana_to_romaji(text):
    text = kata_to_hira(text)
    out, i = [], 0
    while i < len(text):
        if text[i] == "っ" and i + 1 < len(text):
            nxt = ROMA.get(text[i+1:i+3], ROMA.get(text[i+1], ""))
            if nxt:
                out.append("t" if nxt.startswith("ch") else nxt[0])
            i += 1
        elif text[i] == "ー":
            prev = out[-1] if out else ""
            out.append(next((c for c in reversed(prev) if c in "aeiou"), ""))
            i += 1
        else:
            pair = text[i:i+2]
            if pair in ROMA:
                out.append(ROMA[pair])
                i += 2
            else:
                out.append(ROMA.get(text[i], text[i]))
                i += 1
    return "".join(out)

class Token:
    def __init__(self, surface, reading="", lemma="", pos=""):
        self.surface = surface
        self.reading = reading
        self.lemma = lemma or surface
        self.pos = pos

    @property
    def ruby(self):
        return self.reading if KANJI.search(self.surface) else ""

    @property
    def romaji(self):
        if KANJI.search(self.surface) and not self.reading:
            return ""
        return kana_to_romaji(self.reading or self.surface)

def segment(text, parser):
    if parser is None:
        return [Token(c) for c in text]
    try:
        words = parser.safeparse(text)
        if not words or "".join(w.word for w in words) != text:
            raise ValueError("MeCab segmentation did not match original Japanese")
        result = []
        for word in words:
            surface = word.word
            reading = kata_to_hira(str(getattr(word, "kana", "") or ""))
            lemma = str(getattr(word, "prototype", "") or surface)
            pos = str(getattr(word, "wordclass", "") or "")
            m = re.search(r"[\u3040-\u309f]+$", surface)
            if m and KANJI.search(surface[:m.start()]) and reading.endswith(m.group()):
                result.append(Token(surface[:m.start()], reading[:-len(m.group())], lemma, pos))
                result.append(Token(m.group(), m.group(), lemma, pos))
            else:
                result.append(Token(surface, reading, lemma, pos))
        return result
    except Exception:
        return [Token(c) for c in text]

class JMdict:
    def __init__(self):
        self.db = None
        path = USER_DIR / "jmdict.sqlite3"
        if path.exists():
            try:
                self.db = sqlite3.connect(str(path))
                self.db.execute("SELECT term FROM dictionary LIMIT 1")
            except sqlite3.DatabaseError:
                self.db = None

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None

    def lookup(self, token):
        entry = {"word": token.lemma, "reading": token.reading,
                 "pos": token.pos, "meaning": "No JMdict entry found"}
        if self.db is None:
            entry["meaning"] = "Install the offline JMdict database (see docs/study-mode.md)"
            return entry
        for term in dict.fromkeys((token.lemma, token.surface, token.reading)):
            if not term:
                continue
            row = self.db.execute(
                "SELECT term, reading, pos, meanings FROM dictionary "
                "WHERE term=? ORDER BY priority LIMIT 1", (term,)
            ).fetchone()
            if row:
                return dict(zip(("word","reading","pos","meaning"), row))
        return entry

class Options:
    def __init__(self):
        self.values = dict(DEFAULTS)
        for path in (USER_DIR / "overlay_settings.json", USER_DIR / "study_mode.json"):
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    for key, old in DEFAULTS.items():
                        if key in data and type(data[key]) is type(old):
                            self.values[key] = data[key]
                except (OSError, ValueError):
                    pass

    def save(self):
        USER_DIR.mkdir(parents=True, exist_ok=True)
        path = USER_DIR / "study_mode.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.values, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)

class StudyCanvas(QWidget):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.chars, self.hitboxes, self.commands = [], [], []
        self.anchor = self.caret = None
        self.dragging = self.reveal = False
        self.english_bottom = 0
        self.relayout()

    def relayout(self):
        opts = self.view.options.values
        pad = opts["padding"]
        max_x = max(pad + 80, self.width() - pad)
        enfont = QFont("Segoe UI", opts["english_size"])
        jafont = QFont("Yu Gothic", opts["japanese_size"])
        rubyfont = QFont("Yu Gothic", opts["furigana_size"])
        em, jm, rm = (QFontMetrics(f) for f in (enfont,jafont,rubyfont))
        commands, chars, hitboxes = [], [], []
        x = y = pad
        if opts["show_english"] and self.view.english:
            height = em.height() + opts["line_gap"]
            for c in self.view.english:
                if c == "\n":
                    chars.append(("en", c, QRectF(x,y,0,height)))
                    x, y = pad, y + height
                    continue
                w = max(1, em.horizontalAdvance(c))
                if x > pad and x + w > max_x:
                    x, y = pad, y + height
                rect = QRectF(x,y,w,em.height())
                commands.append(("en", c, rect, enfont))
                chars.append(("en",c,rect))
                x += w
            y += height + opts["section_gap"]
        self.english_bottom = y
        x = pad
        if opts["show_japanese"] and self.view.japanese:
            height = rm.height() + jm.height() + opts["line_gap"]
            for token in self.view.tokens:
                if token.surface == "\n":
                    chars.append(("ja","\n",QRectF(x,y,0,height)))
                    x, y = pad, y + height
                    continue
                text_width = jm.horizontalAdvance(token.surface)
                ruby_width = rm.horizontalAdvance(token.ruby) if token.ruby else 0
                width = max(text_width, ruby_width) + (4 if token.ruby else 0)
                if x > pad and x + width > max_x:
                    x, y = pad, y + height
                middle = x + width / 2
                if token.ruby:
                    commands.append(("ruby",token.ruby,
                        QRectF(middle-ruby_width/2,y,ruby_width,rm.height()),rubyfont))
                start = middle - text_width / 2
                commands.append(("ja",token.surface,
                    QRectF(start,y+rm.height(),text_width,jm.height()),jafont))
                offset = start
                for ch in token.surface:
                    cw = max(1,jm.horizontalAdvance(ch))
                    chars.append(("ja",ch,QRectF(offset,y+rm.height(),cw,jm.height())))
                    offset += cw
                hitboxes.append((QRectF(x,y+rm.height(),width,jm.height()),token))
                x += width
            y += height
        self.commands, self.chars, self.hitboxes = commands,chars,hitboxes
        self.setMinimumHeight(max(120,int(y+pad)))
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        alpha = max(0,min(255,int(self.view.options.values["opacity"]*255/100)))
        p.fillRect(self.rect(),QColor(24,25,35,alpha))
        if self.anchor is not None and self.caret is not None:
            start,end = sorted((self.anchor,self.caret))
            for _,c,rect in self.chars[start:end]:
                if c != "\n":
                    p.fillRect(rect,QColor("#4c6696"))
        for typ,s,rect,font in self.commands:
            p.setFont(font)
            p.setPen(QColor("#a5c7ff" if typ == "ruby" else
                         ("#dce0f0" if typ == "en" else "#ffffff")))
            if typ == "en" and self.view.options.values["hide_english"] and not self.reveal:
                s = "•"
            p.drawText(QPointF(rect.x(),rect.y()+QFontMetrics(font).ascent()),s)
        p.end()

    @staticmethod
    def pos(e):
        return e.position() if hasattr(e,"position") else QPointF(e.pos())

    @staticmethod
    def global_pos(e):
        return e.globalPosition().toPoint() if hasattr(e,"globalPosition") else e.globalPos()

    def nearest(self,pos):
        if not self.chars:
            return None
        idx = min(range(len(self.chars)),key=lambda i:
            max(0,self.chars[i][2].top()-pos.y(),pos.y()-self.chars[i][2].bottom())*1000
            + abs(self.chars[i][2].center().x()-pos.x()))
        return idx + (pos.x()>self.chars[idx][2].center().x())

    def token_at(self,pos):
        return next((t for r,t in self.hitboxes if r.contains(pos)),None)

    def mousePressEvent(self,e):
        if e.button() == Qt.MouseButton.RightButton:
            token = self.token_at(self.pos(e))
            if token:
                self.view.pin(token)
            return
        if e.button() == Qt.MouseButton.LeftButton and self.view.options.values["selectable_text"]:
            self.anchor = self.caret = self.nearest(self.pos(e))
            self.dragging = True
            self.setFocus()
            self.update()

    def mouseMoveEvent(self,e):
        if self.dragging:
            self.caret = self.nearest(self.pos(e))
            self.update()
            return
        reveal = (self.view.options.values["hide_english"] and self.view.options.values["show_english"]
                  and self.pos(e).y() < self.english_bottom)
        if reveal != self.reveal:
            self.reveal = reveal
            self.update()
        token = self.token_at(self.pos(e))
        if not token:
            QToolTip.hideText()
            return
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if shift and self.view.options.values["shift_hover_dictionary"]:
            entry = self.view.dictionary.lookup(token)
            QToolTip.showText(self.global_pos(e),
                "{word} [{reading}]\n{pos}\n{meaning}".format(**entry)[:850],self)
        elif self.view.options.values["hover_romaji"] and token.romaji:
            QToolTip.showText(self.global_pos(e),token.romaji,self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self,e):
        if self.dragging:
            self.caret = self.nearest(self.pos(e))
            self.dragging = False
            self.update()

    def leaveEvent(self,e):
        self.reveal = False
        QToolTip.hideText()
        self.update()
        super().leaveEvent(e)

    def keyPressEvent(self,e):
        if e.matches(QKeySequence.StandardKey.Copy):
            self.copy()
        else:
            super().keyPressEvent(e)

    def copy(self):
        if self.anchor is None or self.caret is None:
            return
        lo,hi = sorted((self.anchor,self.caret))
        selected = self.chars[lo:hi]
        out = []
        last = None
        for language,c,_ in selected:
            if last is not None and last != language:
                out.append("\n")
            out.append(c)
            last = language
        QApplication.clipboard().setText("".join(out).strip())

class StudyMode(QWidget):
    def __init__(self,parent):
        super().__init__(parent)
        self.options = Options()
        self.dictionary = JMdict()
        self.english = self.japanese = ""
        self.tokens = []
        self.parser = None
        self.parser_tried = False
        self.pinned = []
        self.setObjectName("StudyMode")
        self.setStyleSheet("QWidget#StudyMode{background:#181923;color:white;}QPushButton{padding:4px}")
        column = QVBoxLayout(self)
        column.setContentsMargins(0,0,0,0)
        column.setSpacing(0)
        toolbar = QWidget(self)
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(76,3,8,3)
        row.addWidget(QLabel("Japanese study mode · Shift + hover: meanings",toolbar))
        row.addStretch()
        settings = QPushButton("Settings",toolbar)
        settings.clicked.connect(self.settings)
        row.addWidget(settings)
        column.addWidget(toolbar)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.canvas = StudyCanvas(self)
        self.scroll.setWidget(self.canvas)
        self.scroll.viewport().installEventFilter(self)
        column.addWidget(self.scroll)

    def eventFilter(self,obj,event):
        if obj is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self.canvas.setMinimumWidth(self.scroll.viewport().width())
            self.canvas.relayout()
        return super().eventFilter(obj,event)

    def get_parser(self):
        if not self.parser_tried:
            self.parser_tried = True
            try:
                from myutils.mecab import mecab
                self.parser = mecab()
            except Exception:
                self.parser = None
        return self.parser

    def set_english(self,s):
        if not isinstance(s,str) or not s or self.english == s:
            return
        self.english, self.japanese, self.tokens = s,"",[]
        self.canvas.anchor = self.canvas.caret = None
        self.canvas.relayout()

    def set_japanese(self,s):
        if not isinstance(s,str) or not JAPANESE.search(s) or self.japanese == s:
            return
        self.japanese = s
        self.tokens = segment(s,self.get_parser())
        self.canvas.anchor = self.canvas.caret = None
        self.canvas.relayout()

    def pin(self,token):
        entry = self.dictionary.lookup(token)
        d = QDialog(self)
        d.setWindowTitle("JMdict: "+token.surface)
        d.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        d.setWindowFlag(Qt.WindowType.Window,True)
        d.resize(430,210)
        l = QVBoxLayout(d)
        w = QLabel(entry["word"],d)
        w.setStyleSheet("font-size:24px;font-weight:bold")
        l.addWidget(w)
        l.addWidget(QLabel("{}  ·  {}".format(entry["reading"],token.romaji),d))
        l.addWidget(QLabel(entry["pos"],d))
        m = QLabel(entry["meaning"],d)
        m.setWordWrap(True)
        l.addWidget(m)
        l.addStretch()
        copy = QPushButton("Copy vocabulary (word / reading / meaning)",d)
        copy.clicked.connect(lambda: QApplication.clipboard().setText(
            "{}\t{}\t{}".format(entry["word"],entry["reading"],entry["meaning"])))
        l.addWidget(copy)
        self.pinned.append(d)
        d.destroyed.connect(lambda: self.pinned.remove(d) if d in self.pinned else None)
        d.show()

    def settings(self):
        d = QDialog(self)
        d.setWindowTitle("Japanese Study Mode settings")
        form = QFormLayout(d)
        def change(k,v):
            self.options.values[k] = v
            self.options.save()
            self.canvas.relayout()
        for label,k,low,high in (
            ("English font size","english_size",10,44),
            ("Japanese font size","japanese_size",12,52),
            ("Furigana font size","furigana_size",8,30),
            ("Section gap","section_gap",0,60),
            ("Line gap","line_gap",0,40),
            ("Padding","padding",4,70),
            ("Background opacity (%)","opacity",40,100)):
            v = QSpinBox(d)
            v.setRange(low,high)
            v.setValue(self.options.values[k])
            v.valueChanged.connect(lambda value,key=k:change(key,value))
            form.addRow(label,v)
        for label,k in (
            ("Show English","show_english"),
            ("Show Japanese","show_japanese"),
            ("Hide English until hover","hide_english"),
            ("Romaji on hover","hover_romaji"),
            ("Selectable text","selectable_text"),
            ("Definitions on Shift + hover","shift_hover_dictionary")):
            v = QCheckBox(label,d)
            v.setChecked(self.options.values[k])
            v.toggled.connect(lambda value,key=k:change(key,value))
            form.addRow(v)
        close = QPushButton("Close",d)
        close.clicked.connect(d.accept)
        form.addRow(close)
        d.exec()
