from __future__ import annotations

from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo
from aqt import gui_hooks
from aqt.webview import AnkiWebView

import copy
import json
import re


ADDON_NAME = __name__  # this add-on folder name


# ========= Shipped defaults =========

DEFAULT_CONF: dict = {
    "enabled": True,
    "languages": [
        "en-US",
        "ja-JP",
    ],
    "voices": {
        "en-US": [
            "",
            "Microsoft David",
            "Microsoft Zira",
        ],
        "ja-JP": [
            "",
            "Microsoft Haruka",
            "Microsoft Sayaka",
        ],
    },
    "fieldSettings": {},
}


# ========= Utilities =========

def get_conf() -> dict:
    """Return current config; if none, write shipped defaults first."""
    conf = mw.addonManager.getConfig(ADDON_NAME)
    if conf is None:
        conf = copy.deepcopy(DEFAULT_CONF)
        mw.addonManager.writeConfig(ADDON_NAME, conf)
    return conf


def write_conf(conf: dict) -> None:
    mw.addonManager.writeConfig(ADDON_NAME, conf)


def reset_conf_to_defaults() -> dict:
    """Overwrite config with shipped defaults and return the new config."""
    conf = copy.deepcopy(DEFAULT_CONF)
    write_conf(conf)
    return conf


def escape_attr(s: str) -> str:
    """Escape for HTML attributes."""
    if s is None:
        return ""
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&#39;")
    )


# ========= Initialize fieldSettings =========

def ensure_field_settings() -> None:
    """
    Ensure fieldSettings covers all current note types/fields.
    (Adds missing entries; doesn't delete existing ones.)
    """
    conf = get_conf()
    field_settings = conf.get("fieldSettings", {})

    col = mw.col
    if not col:
        return

    for model in col.models.all():
        mid = str(model["id"])
        if mid not in field_settings:
            field_settings[mid] = {}

        mconf = field_settings[mid]
        for fld in model["flds"]:
            fname = fld["name"]
            if fname not in mconf:
                mconf[fname] = {
                    "enabled": False,
                    "lang": "ja-JP",
                    "voice": "",
                }

    conf["fieldSettings"] = field_settings
    write_conf(conf)


# ========= Config Dialog =========

class TtsConfigDialog(QDialog):
    """
    Note type × field settings:
      - enabled (per field)
      - lang
      - voice
    Plus:
      - global enable toggle
      - reset to defaults
    """

    def __init__(self, mw: "aqt.main.AnkiQt"):
        super().__init__(mw)
        self.mw = mw

        self.setWindowTitle("TTS Auto Helper Configuration")
        self.resize(700, 420)

        self.conf = get_conf()
        ensure_field_settings()
        self.field_settings: dict = self.conf.get("fieldSettings", {})

        # Prefer auto-detected voices if available
        auto_langs = self.conf.get("languages_auto")
        auto_voices = self.conf.get("voices_auto")

        if auto_langs and auto_voices:
            self.lang_list = auto_langs
            self.voice_map = auto_voices
        else:
            self.lang_list = self.conf.get("languages", ["en-US", "ja-JP"])
            self.voice_map = self.conf.get("voices", {})

        self.col = mw.col
        self.models_by_id: dict[str, dict] = {}
        self.model_ids: list[str] = []
        if self.col:
            for m in self.col.models.all():
                mid = str(m["id"])
                self.models_by_id[mid] = m
                self.model_ids.append(mid)

        # ---- Layout ----
        main_layout = QVBoxLayout(self)

        # Global enable toggle
        self.enabled_chk = QCheckBox("Enable TTS Auto Helper")
        self.enabled_chk.setChecked(bool(self.conf.get("enabled", True)))
        main_layout.addWidget(self.enabled_chk)

        # Note type selector
        top_layout = QHBoxLayout()
        lbl = QLabel("Note types:")
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(250)

        for mid in self.model_ids:
            m = self.models_by_id[mid]
            name = m["name"]
            self.model_combo.addItem(f"{name} ({mid})", userData=mid)

        top_layout.addWidget(lbl)
        top_layout.addWidget(self.model_combo, 1)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        # Fields table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Fields", "Enabled", "Languages", "Voices"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        main_layout.addWidget(self.table, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_reset = QPushButton("Reset to defaults")
        btn_layout.addWidget(self.btn_reset)
        btn_layout.addStretch()
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Cancel")
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(btn_layout)

        # Signals
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_reset.clicked.connect(self.on_reset_defaults)

        # Load first model
        if self.model_ids:
            self.on_model_changed(0)

        QTimer.singleShot(0, self._center_on_parent)

        # (Voice probing runs once on profile load to avoid UI glitches on repeated opens)

    # ---- Table load ----

    def on_model_changed(self, idx: int) -> None:
        mid = self.model_combo.currentData()
        if not mid:
            return

        model = self.models_by_id.get(mid)
        if not model:
            return

        mconf = self.field_settings.get(mid, {})
        flds = model["flds"]

        self.table.setRowCount(len(flds))

        for row, fld in enumerate(flds):
            fname = fld["name"]

            # (1) Field name (read-only)
            item_name = QTableWidgetItem(fname)
            item_name.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, item_name)

            fconf = mconf.get(fname, {})

            # (2) Enabled checkbox
            chk = QCheckBox()
            chk.setChecked(bool(fconf.get("enabled", False)))
            cell_widget_chk = QWidget()
            lay_chk = QHBoxLayout(cell_widget_chk)
            lay_chk.setContentsMargins(0, 0, 0, 0)
            lay_chk.addWidget(chk, alignment=Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 1, cell_widget_chk)

            # (3) Language combo
            combo_lang = QComboBox()
            for lang in self.lang_list:
                combo_lang.addItem(lang)
            cur_lang = fconf.get("lang", self.lang_list[0] if self.lang_list else "")
            if cur_lang in self.lang_list:
                combo_lang.setCurrentText(cur_lang)

            # (4) Voice combo
            combo_voice = QComboBox()
            cur_voice = fconf.get("voice", "")
            self._update_voice_combo(combo_voice, cur_lang, cur_voice)

            # Update voice list when language changes
            def on_lang_changed(new_lang, vc=combo_voice):
                self._update_voice_combo(vc, new_lang, None)

            combo_lang.currentTextChanged.connect(on_lang_changed)

            self.table.setCellWidget(row, 2, combo_lang)
            self.table.setCellWidget(row, 3, combo_voice)

    def _update_voice_combo(self, combo: QComboBox, lang: str, selected: str | None) -> None:
        combo.clear()
        voices_for_lang = self.voice_map.get(lang, [])
        if not voices_for_lang:
            voices_for_lang = [""]

        for v in voices_for_lang:
            combo.addItem(v)

        if selected and selected in voices_for_lang:
            combo.setCurrentText(selected)

    # ---- Save / Reset ----

    def accept(self) -> None:
        # Save current model before closing
        mid = self.model_combo.currentData()
        if mid:
            self._save_current_model_settings(mid)

        # Save global enable toggle
        self.conf["enabled"] = bool(self.enabled_chk.isChecked())

        # Save table settings
        self.conf["fieldSettings"] = self.field_settings
        write_conf(self.conf)

        # Re-ensure structure
        ensure_field_settings()

        super().accept()

    def _save_current_model_settings(self, mid: str) -> None:
        model = self.models_by_id.get(mid)
        if not model:
            return

        flds = model["flds"]
        rows = self.table.rowCount()
        if rows != len(flds):
            rows = min(rows, len(flds))

        mconf = self.field_settings.get(mid, {})
        if mconf is None:
            mconf = {}
            self.field_settings[mid] = mconf

        for row in range(rows):
            fname = flds[row]["name"]

            # enabled
            enabled = False
            cell_chk = self.table.cellWidget(row, 1)
            if cell_chk:
                chk = cell_chk.findChild(QCheckBox)
                if chk:
                    enabled = chk.isChecked()

            # lang
            lang_val = ""
            combo_lang = self.table.cellWidget(row, 2)
            if isinstance(combo_lang, QComboBox):
                lang_val = combo_lang.currentText()

            # voice
            voice_val = ""
            combo_voice = self.table.cellWidget(row, 3)
            if isinstance(combo_voice, QComboBox):
                voice_val = combo_voice.currentText()

            mconf[fname] = {
                "enabled": enabled,
                "lang": lang_val,
                "voice": voice_val,
            }

        self.field_settings[mid] = mconf

    def on_reset_defaults(self) -> None:
        # Save pending edits (table widgets are not auto-synced)
        mid = self.model_combo.currentData()
        if mid:
            self._save_current_model_settings(mid)

        resp = QMessageBox.question(
            self,
            "Reset to defaults",
            "This will overwrite your current add-on settings with the shipped defaults.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        # Overwrite config then rebuild fieldSettings
        self.conf = reset_conf_to_defaults()
        ensure_field_settings()
        self.conf = get_conf()
        self.field_settings = self.conf.get("fieldSettings", {})

        # Reload voice lists (prefer auto if present)
        auto_langs = self.conf.get("languages_auto")
        auto_voices = self.conf.get("voices_auto")
        if auto_langs and auto_voices:
            self.lang_list = auto_langs
            self.voice_map = auto_voices
        else:
            self.lang_list = self.conf.get("languages", ["en-US", "ja-JP"])
            self.voice_map = self.conf.get("voices", {})

        self.enabled_chk.setChecked(bool(self.conf.get("enabled", True)))

        idx = self.model_combo.currentIndex()
        if idx >= 0:
            self.on_model_changed(idx)

    # ---- Hidden WebView: probe voice list ----

    def _probe_voices_via_webview(self) -> None:
        """Run speechSynthesis.getVoices() in a hidden webview and store results."""
        if not self.col:
            return

        self._voice_web = AnkiWebView(self)
        self._voice_web.hide()
        self._voice_web.set_bridge_command(self._on_voice_bridge_cmd, self)

        html_doc = '''
        <html><body>
        <script>
        (function() {
            function sendVoices(list) {
                if (!window.pycmd || !list || !list.length) return;
                try {
                    var data = list.map(function(v){ return { name: v.name, lang: v.lang }; });
                    pycmd("voices:" + JSON.stringify(data));
                } catch (e) {}
            }
            function main() {
                if (!("speechSynthesis" in window)) return;
                var v = window.speechSynthesis.getVoices();
                if (v && v.length > 0) {
                    sendVoices(v);
                } else {
                    window.speechSynthesis.onvoiceschanged = function() {
                        var v2 = window.speechSynthesis.getVoices();
                        sendVoices(v2);
                    };
                }
            }
            main();
        })();
        </script>
        </body></html>
        '''
        self._voice_web.stdHtml(html_doc)

    def _on_voice_bridge_cmd(self, cmd: str) -> None:
        if not cmd.startswith("voices:"):
            return

        data_json = cmd[len("voices:"):]
        try:
            voice_list = json.loads(data_json)
        except Exception:
            return

        voices_by_lang: dict[str, list[str]] = {}
        for v in voice_list:
            lang = v.get("lang") or ""
            name = v.get("name") or ""
            if not lang:
                continue
            voices_by_lang.setdefault(lang, [])
            if name and name not in voices_by_lang[lang]:
                voices_by_lang[lang].append(name)

        self.conf["voices_auto"] = voices_by_lang
        self.conf["languages_auto"] = sorted(voices_by_lang.keys())
        write_conf(self.conf)

        # Update dialog lists
        self.lang_list = self.conf["languages_auto"]
        self.voice_map = self.conf["voices_auto"]

        # Refresh current table
        idx = self.model_combo.currentIndex()
        if idx >= 0:
            self.on_model_changed(idx)

        if getattr(self, "_voice_web", None):
            self._voice_web.deleteLater()
            self._voice_web = None

    def _center_on_parent(self) -> None:
        try:
            p = self.parentWidget()
            if p:
                pg = p.frameGeometry()
                cg = self.frameGeometry()
                cg.moveCenter(pg.center())
                self.move(cg.topLeft())
                return

            # fallback: center on current screen
            app = QGuiApplication.instance() if "QGuiApplication" in globals() else QApplication.instance()
            if app:
                screen = app.primaryScreen().availableGeometry()
                cg = self.frameGeometry()
                cg.moveCenter(screen.center())
                self.move(cg.topLeft())
        except Exception:
            pass



# ========= Browser-side JS =========

TTS_JS = r'''
<script>
(function() {

    function speak(text, lang, voiceName, onDone) {
        if (!("speechSynthesis" in window)) {
            alert("TTS is not supported in this environment.");
            if (onDone) { onDone(); }
            return;
        }

        var u = new SpeechSynthesisUtterance(text || "");
        if (lang) { u.lang = lang; }

        if (onDone) {
            u.onend = onDone;
            u.onerror = onDone;
        }

        function applyVoice() {
            if (!voiceName) { return; }
            var voices = window.speechSynthesis.getVoices() || [];
            for (var i = 0; i < voices.length; i++) {
                var v = voices[i];
                if (v.name === voiceName) {
                    u.voice = v;
                    break;
                }
            }
        }

        var voices = window.speechSynthesis.getVoices();
        if (voices && voices.length > 0) {
            applyVoice();
            window.speechSynthesis.cancel();
            window.speechSynthesis.speak(u);
        } else {
            window.speechSynthesis.onvoiceschanged = function() {
                applyVoice();
                window.speechSynthesis.cancel();
                window.speechSynthesis.speak(u);
            };
        }
    }

    // Manual click play
    if (!window._ttsAutoHelperInitialized) {
        window._ttsAutoHelperInitialized = true;
        document.addEventListener("click", function(ev) {
            var btn = ev.target.closest(".tts-auto-helper-btn");
            if (!btn) return;
            var text = btn.getAttribute("data-tts-text") || "";
            var lang = btn.getAttribute("data-tts-lang") || "";
            var voice = btn.getAttribute("data-tts-voice") || "";
            speak(text, lang, voice, null);
        });
    }

    // Auto play all enabled buttons sequentially
    function autoPlayAllButtons() {
        var btns = document.querySelectorAll(".tts-auto-helper-btn");
        if (!btns || btns.length === 0) return;

        var list = Array.prototype.slice.call(btns);
        var idx = 0;

        function playNext() {
            if (idx >= list.length) return;
            var b = list[idx++];
            var text = b.getAttribute("data-tts-text") || "";
            var lang = b.getAttribute("data-tts-lang") || "";
            var voice = b.getAttribute("data-tts-voice") || "";
            speak(text, lang, voice, playNext);
        }

        playNext();
    }

    if (document.readyState === "complete" || document.readyState === "interactive") {
        setTimeout(autoPlayAllButtons, 10);
    } else {
        document.addEventListener("DOMContentLoaded", function() {
            setTimeout(autoPlayAllButtons, 10);
        });
    }
})();
</script>
'''



# ========= Voice probing (run once per profile) =========

_VOICE_PROBE_WEB: AnkiWebView | None = None
_VOICE_PROBED: bool = False

_VOICE_PROBE_HTML = '''
<html><body>
<script>
(function() {
    function sendVoices(list) {
        if (!window.pycmd || !list || !list.length) return;
        try {
            var data = list.map(function(v){ return { name: v.name, lang: v.lang }; });
            pycmd("voices:" + JSON.stringify(data));
        } catch (e) {}
    }
    function main() {
        if (!("speechSynthesis" in window)) return;
        var v = window.speechSynthesis.getVoices();
        if (v && v.length > 0) {
            sendVoices(v);
        } else {
            window.speechSynthesis.onvoiceschanged = function() {
                var v2 = window.speechSynthesis.getVoices();
                sendVoices(v2);
            };
        }
    }
    main();
})();
</script>
</body></html>
'''

def _on_voice_probe_cmd(cmd: str) -> None:
    global _VOICE_PROBE_WEB, _VOICE_PROBED
    if not cmd.startswith("voices:"):
        return

    data_json = cmd[len("voices:"):]
    try:
        voice_list = json.loads(data_json)
    except Exception:
        return

    voices_by_lang: dict[str, list[str]] = {}
    for v in voice_list:
        lang = v.get("lang") or ""
        name = v.get("name") or ""
        if not lang:
            continue
        voices_by_lang.setdefault(lang, [])
        if name and name not in voices_by_lang[lang]:
            voices_by_lang[lang].append(name)

    conf = get_conf()
    conf["voices_auto"] = voices_by_lang
    conf["languages_auto"] = sorted(voices_by_lang.keys())
    write_conf(conf)

    _VOICE_PROBED = True

    if _VOICE_PROBE_WEB is not None:
        _VOICE_PROBE_WEB.deleteLater()
        _VOICE_PROBE_WEB = None

def _start_voice_probe() -> None:
    """Probe TTS voices once per profile (without tying it to the config dialog)."""
    global _VOICE_PROBE_WEB, _VOICE_PROBED
    if _VOICE_PROBED:
        return
    if not mw.col:
        return

    conf = get_conf()
    # If already cached, don't probe again
    if conf.get("voices_auto") and conf.get("languages_auto"):
        _VOICE_PROBED = True
        return

    if _VOICE_PROBE_WEB is not None:
        return

    _VOICE_PROBE_WEB = AnkiWebView(mw)
    _VOICE_PROBE_WEB.hide()
    _VOICE_PROBE_WEB.set_bridge_command(_on_voice_probe_cmd, mw)
    _VOICE_PROBE_WEB.stdHtml(_VOICE_PROBE_HTML)



# ========= Card hook =========

def inject_tts_buttons(html_text: str, card, kind: str) -> str:
    conf = get_conf()
    if not conf.get("enabled", True):
        return html_text

    col = mw.col
    if not col:
        return html_text

    note = card.note()
    model = note.note_type()
    mid = str(model["id"])

    field_settings = conf.get("fieldSettings", {})
    model_conf = field_settings.get(mid)
    if not model_conf:
        return html_text

    model_fields = model["flds"]
    field_names = [fld["name"] for fld in model_fields]

    target_field_names: list[str] = []
    try:
        tmpls = model["tmpls"]
        tmpl = tmpls[card.ord] if card.ord < len(tmpls) else tmpls[0]

        if kind == "reviewAnswer":
            afmt = tmpl.get("afmt", "")
            idx = afmt.find('id="answer"')
            if idx == -1:
                idx = afmt.find("id=answer")
            search_part = afmt[idx:] if idx != -1 else afmt
        else:
            search_part = tmpl.get("qfmt", "")

        for m in re.finditer(r"{{([^}]+)}}", search_part):
            name = m.group(1).strip()
            if name in field_names and name not in target_field_names:
                target_field_names.append(name)

    except Exception:
        target_field_names = []

    if not target_field_names:
        target_field_names = field_names[:]

    blocks: list[str] = []

    for fname in target_field_names:
        fconf = model_conf.get(fname)
        if not fconf or not fconf.get("enabled"):
            continue

        try:
            text = note[fname]
        except KeyError:
            continue

        if not text:
            continue

        lang = fconf.get("lang", "")
        voice = fconf.get("voice", "")

        btn_html = (
            '<button class="tts-auto-helper-btn" '
            f'data-tts-text="{escape_attr(text)}" '
            f'data-tts-lang="{escape_attr(lang)}" '
            f'data-tts-voice="{escape_attr(voice)}" '
            'style="margin: 2px; padding: 2px 6px; font-size: 12px;">'
            '🔊 ' + escape_attr(fname) +
            '</button>'
        )
        blocks.append(btn_html)

    if not blocks:
        return html_text

    container = (
        '<div class="tts-auto-helper-container" '
        'style="margin-top: 8px; border-top: 1px solid #ddd; padding-top: 4px;">'
        + "".join(blocks) +
        "</div>"
    )

    if "_ttsAutoHelperInitialized" not in html_text:
        html_text += TTS_JS

    html_text += container
    return html_text


# ========= Entry points =========

def open_tts_config_dialog():
    if not mw.col:
        showInfo("No collection opened")
        return
    ensure_field_settings()
    dlg = TtsConfigDialog(mw)
    dlg.exec()


def setup_config_action():
    # Tools → Add-ons → (this add-on) → Config opens this dialog
    mw.addonManager.setConfigAction(ADDON_NAME, open_tts_config_dialog)


# ========= Startup hooks =========

_TTS_AUTO_HELPER_INITIALIZED = False


def on_profile_loaded() -> None:
    global _TTS_AUTO_HELPER_INITIALIZED

    ensure_field_settings()
    _start_voice_probe()
    setup_config_action()

    # Avoid duplicate hook registration on some reload patterns
    if not _TTS_AUTO_HELPER_INITIALIZED:
        gui_hooks.card_will_show.append(inject_tts_buttons)
        _TTS_AUTO_HELPER_INITIALIZED = True


gui_hooks.profile_did_open.append(on_profile_loaded)
