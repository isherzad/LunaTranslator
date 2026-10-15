"""One-time downloader/indexer for the offline JMdict English dictionary.

Usage (on Windows): py -3.12 -m pip install lxml
                    py -3.12 src/LunaTranslator/gui/study_dictionary_install.py
After installation the Study Mode interface performs only SQLite lookups.
"""
import gzip
import sqlite3
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "userconfig"
DB = ROOT / "jmdict.sqlite3"
URLS = (
    "https://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz",
    "https://www.edrdg.org/pub/Nihongo/JMdict_e.gz",
)

def build():
    ROOT.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        print("Already installed:", DB)
        return
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "JMdict_e.gz"
        for url in URLS:
            try:
                print("Downloading:", url, flush=True)
                urllib.request.urlretrieve(url, source)
                break
            except Exception as error:
                print("Download failed:", error)
        else:
            raise RuntimeError("Unable to download JMdict; verify your internet connection")

        from lxml import etree
        temporary_db = ROOT / "jmdict.sqlite3.tmp"
        temporary_db.unlink(missing_ok=True)
        conn = sqlite3.connect(str(temporary_db))
        try:
            conn.execute("CREATE TABLE dictionary ("
                         "term TEXT NOT NULL, reading TEXT, pos TEXT, "
                         "meanings TEXT, priority INTEGER)")
            batch = []
            with gzip.open(source, "rb") as stream:
                entries = etree.iterparse(stream, events=("end",), tag="entry",
                                          resolve_entities=True, huge_tree=True)
                for _, element in entries:
                    spellings = [node.text for node in element.findall("./k_ele/keb") if node.text]
                    readings = [node.text for node in element.findall("./r_ele/reb") if node.text]
                    meanings, pos = [], []
                    for sense in element.findall("./sense"):
                        for gloss in sense.findall("./gloss"):
                            lang = gloss.get("{http://www.w3.org/XML/1998/namespace}lang")
                            if gloss.text and lang in (None, "eng"):
                                meanings.append(gloss.text)
                        for part in sense.findall("./pos"):
                            if part.text and part.text not in pos:
                                pos.append(part.text)
                    if meanings:
                        english = "; ".join(dict.fromkeys(meanings))[:950]
                        category = ", ".join(pos)[:180]
                        priority = 0 if element.find(".//ke_pri") is not None else 1
                        for text in spellings:
                            batch.append((text, readings[0] if readings else "",
                                          category, english, priority))
                        for text in readings:
                            batch.append((text, text, category, english, priority+1))
                    if len(batch) > 3000:
                        conn.executemany("INSERT INTO dictionary VALUES (?,?,?,?,?)", batch)
                        batch.clear()
                    element.clear()
                    while element.getprevious() is not None:
                        del element.getparent()[0]
            if batch:
                conn.executemany("INSERT INTO dictionary VALUES (?,?,?,?,?)", batch)
            conn.execute("CREATE INDEX idx_study_term ON dictionary (term, priority)")
            conn.commit()
        except Exception:
            conn.close()
            temporary_db.unlink(missing_ok=True)
            raise
        conn.close()
        temporary_db.replace(DB)
        print("JMdict installed successfully:", DB)

if __name__ == "__main__":
    build()
