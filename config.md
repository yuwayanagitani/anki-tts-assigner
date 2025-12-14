# TTS Auto Helper – Configuration Guide

TTS Auto Helper adds TTS (text-to-speech) buttons to cards **without modifying card templates**.  
When enabled, it automatically reads aloud all enabled fields in order, both on the front and back of cards.

This document describes all available configuration options.

---

## Basic structure (config.json)

```jsonc
{
  "enabled": true,
  "languages": ["en-US", "ja-JP"],
  "voices": {
    "en-US": ["Microsoft David", "Microsoft Zira"],
    "ja-JP": ["Microsoft Haruka", "Microsoft Sayaka"]
  },
  "fieldSettings": {}
}
```

The add-on automatically creates `fieldSettings` for each note type on first launch.

---

## Options

### **enabled**
- `true` → TTS Auto Helper is active  
- `false` → completely disabled  

### **languages**
Initial language list for TTS options.  
If **voice auto-detection** is supported on your platform, the add-on replaces this with real system languages.

### **voices**
Initial voice list for each language.  
Also replaced by automatically detected voices when possible.

### **fieldSettings**
Automatically populated based on your note types:

```jsonc
"fieldSettings": {
  "1234567890123": {
    "Front": {
      "enabled": true,
      "lang": "en-US",
      "voice": "Microsoft David"
    },
    "Back": {
      "enabled": true,
      "lang": "ja-JP",
      "voice": "Microsoft Haruka"
    }
  }
}
```

Each field supports:

| Key       | Description |
|-----------|-------------|
| `enabled` | Whether the field is read aloud |
| `lang`    | TTS language code |
| `voice`   | System voice name (depends on OS) |

These settings can also be edited in **Tools → TTS Auto Helper Settings** via GUI.

---

## How it works

- Adds TTS buttons to card rendering **only while the add-on is enabled**  
- Reads aloud **all enabled fields in order**, automatically  
- On back of card, only fields **appearing after `id="answer"`** are targeted  
- Respects custom templates  
- Does **not** modify your note type or fields  
- Automatically detects available TTS voices via a hidden WebView

---

## Notes

- If your system or browser engine does not support Web Speech API, auto-detection of voices may not work.
- This add-on does not change card templates, so it can be safely enabled/disabled at any time.
- Works with Anki 24.x (Qt6 WebEngine).

---

## Troubleshooting

### Buttons do not appear
Check that:
- The add-on is **enabled**
- The field is enabled in GUI settings
- The card template actually includes the field

### Nothing is spoken
Your OS may not provide WebSpeech voices.  
Try switching to another language or voice in settings.

---

## License
MIT (or your preferred license)
