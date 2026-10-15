# Integrated Japanese Study Mode (experimental)

This branch adds an opt-in **Study** view inside LunaTranslator's translation window.
It's designed for an English-patched visual novel hooked as **English source → Japanese translation**. It doesn't change the selected translator (Google works), game patch, original renderer, or normal settings.

## Features
- English source above Japanese translation, with optional English hiding
- Furigana above Japanese kanji using LunaTranslator's configured **MeCab** parser
- **Hover**: romaji; **Shift + hover**: offline dictionary definition
- **Right-click** Japanese word: pin a vocabulary card; copy lemma, reading and meaning
- Mouse selection and Ctrl+C copying
- Font sizes, spacing, opacity and visibility in the integrated Settings dialog
- Imports overlapping values from an older `overlay_settings.json`; saves to `study_mode.json`

## Setup
1. Build/run this branch using [LunaTranslator's upstream instructions](https://github.com/HIllya51/LunaTranslator).
2. Install and configure MeCab/UniDic in LunaTranslator for Japanese readings. Without it, Japanese is displayed without invented furigana.
3. Install an offline English JMdict index once, on a machine with network access:
   ```powershell
   py -3.12 -m pip install lxml
   py -3.12 src/LunaTranslator/gui/study_dictionary_install.py
   ```
   The resulting database is stored in `src/userconfig/jmdict.sqlite3`. The dictionary installer downloads the JMdict data from EDRDG. Observe JMdict licensing if redistributing it.
4. Configure text hooking and translation as before. In the translation window click **Study**, or use **Ctrl+Shift+J** when the window has focus. Click **Settings** for display preferences.

## Existing overlay settings
Optionally copy your old `overlay_settings.json` to `src/userconfig/overlay_settings.json`. Compatible keys are imported and can be overridden in the Study Mode settings.

## Known limitations
- **Experimental source integration; no Windows GUI/runtime build has been validated.** It is not a prebuilt Windows executable.
- Offline dictionary installation requires an initial download and `lxml`.
- Furigana, inflected word lemmas and JMdict entries can be wrong for contextual readings, colloquial expressions or proper names.
- If multiple translation engines are enabled, the study panel shows the most recently delivered Japanese result.
- English hiding is visual only, and selected text can still be copied.
- The mode is aimed at a horizontal Japanese display; the normal LunaTranslator renderer remains available via the toggle.

This branch adds `src/LunaTranslator/gui/study_mode.py` and `study_dictionary_install.py`, and hooks into `translatorUI.py`. The change is isolated and can be reversed by switching back to `main`.
