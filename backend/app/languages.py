try:
    import pycountry
except Exception:  # pragma: no cover
    pycountry = None

# ISO 639-1 language list. pycountry is used when available; the fallback keeps the
# EAS languages plus a few common European languages so the app still works offline.
if pycountry:
    LANGUAGES = sorted(
        [
            {"code": lang.alpha_2, "name": lang.name}
            for lang in pycountry.languages
            if hasattr(lang, "alpha_2") and hasattr(lang, "name")
        ],
        key=lambda item: item["name"].lower(),
    )
else:
    LANGUAGES = [
        {"code": "bg", "name": "Bulgarian"}, {"code": "cs", "name": "Czech"},
        {"code": "da", "name": "Danish"}, {"code": "de", "name": "German"},
        {"code": "el", "name": "Greek"}, {"code": "en", "name": "English"},
        {"code": "es", "name": "Spanish"}, {"code": "et", "name": "Estonian"},
        {"code": "fi", "name": "Finnish"}, {"code": "fr", "name": "French"},
        {"code": "ga", "name": "Irish"}, {"code": "hr", "name": "Croatian"},
        {"code": "hu", "name": "Hungarian"}, {"code": "it", "name": "Italian"},
        {"code": "lt", "name": "Lithuanian"}, {"code": "lv", "name": "Latvian"},
        {"code": "mt", "name": "Maltese"}, {"code": "nl", "name": "Dutch"},
        {"code": "pl", "name": "Polish"}, {"code": "pt", "name": "Portuguese"},
        {"code": "ro", "name": "Romanian"}, {"code": "sk", "name": "Slovak"},
        {"code": "sl", "name": "Slovenian"}, {"code": "sv", "name": "Swedish"},
        {"code": "uk", "name": "Ukrainian"}, {"code": "no", "name": "Norwegian"},
    ]

LANGUAGE_NAMES = {item["code"]: item["name"] for item in LANGUAGES}
