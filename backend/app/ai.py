import os
import re
from urllib.parse import urlencode

import requests
from openai import OpenAI

from .languages import LANGUAGE_NAMES

STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "must", "should", "can", "may",
    "are", "is", "be", "been", "being", "into", "onto", "their", "there", "where", "when",
    "then", "than", "which", "will", "also", "only", "such", "used", "using", "after",
    "before", "during", "between", "within", "without", "under", "over", "tree", "trees",
    "shall", "have", "has", "had", "not", "all", "any", "each", "other", "wherever", "very",
}

BUILT_IN_TERMS = {
    "root collar": {"cs": "kořenový krček"},
    "planting pit": {"cs": "výsadbová jáma"},
    "root ball": {"cs": "kořenový bal"},
    "root system": {"cs": "kořenový systém"},
    "structural soil": {"cs": "strukturální substrát"},
    "soil compaction": {"cs": "zhutnění půdy"},
    "planting stock": {"cs": "výsadbový materiál"},
    "biosecurity": {"cs": "biologická bezpečnost"},
    "mulch": {"cs": "mulč"},
    "watering ring": {"cs": "závlahová mísa"},
    "anchorage system": {"cs": "kotvicí systém"},
    "stem protection": {"cs": "ochrana kmene"},
    "rootable volume": {"cs": "prokořenitelný prostor"},
    "waterlogged soils": {"cs": "zamokřené půdy"},
    "invasive species": {"cs": "invazní druhy"},
}

ADJECTIVE_SUFFIXES = (
    "al", "ial", "ic", "ical", "ive", "ous", "eous", "ious", "ary", "ory", "ent", "ant",
    "able", "ible", "less", "ful", "ed", "ing", "en", "ate", "y",
)

NOUN_HINT_SUFFIXES = (
    "tion", "sion", "ment", "ness", "ity", "ance", "ence", "ure", "age", "ing", "ism", "er", "or",
    "ist", "ics", "sis", "th", "ship", "work", "wood", "soil", "tree", "root", "stem", "pit", "ball",
    "system", "volume", "material", "surface", "site", "zone", "space", "condition", "species",
)

KNOWN_ADJECTIVES = {
    "rootable", "structural", "organic", "inorganic", "urban", "natural", "regional", "national",
    "mechanical", "biological", "chemical", "physical", "sustainable", "underground", "aboveground",
    "above-ground", "below-ground", "bare-rooted", "container-grown", "open-grown", "young",
    "mature", "invasive", "protective", "temporary", "permanent", "suitable", "sufficient", "high",
    "low", "good", "poor", "normal", "annual", "woody", "fine", "lateral", "structural", "rooted",
}


def _clean_text(value: str) -> str:
    value = (value or "").replace("\u00ad", "").replace("￾", " ")
    value = re.sub(r"(?<=[A-Za-z])[-‐‑‒–—]\s+(?=[a-z])", "", value)
    value = re.sub(r"(?<=[A-Za-z])\s+[-‐‑‒–—]\s+(?=[a-z])", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _is_probable_adjective(word: str) -> bool:
    w = word.lower().strip("-–—")
    if len(w) < 4 or w in STOP_WORDS:
        return False
    return w in KNOWN_ADJECTIVES or w.endswith(ADJECTIVE_SUFFIXES)


def _is_probable_noun(word: str) -> bool:
    w = word.lower().strip("-–—")
    if len(w) < 3 or w in STOP_WORDS:
        return False
    if w.endswith("s") and len(w) > 4:
        return True
    return w.endswith(NOUN_HINT_SUFFIXES) or w not in KNOWN_ADJECTIVES


def extract_adjective_noun_terms(source_text: str, limit: int = 30) -> list[dict]:
    text = _clean_text(source_text)
    tokens = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text)
    results: dict[str, float] = {}

    for i in range(len(tokens) - 1):
        a, n = tokens[i], tokens[i + 1]
        phrase = f"{a} {n}".lower()
        if _is_probable_adjective(a) and _is_probable_noun(n):
            if not any(part in STOP_WORDS for part in phrase.split()):
                results[phrase] = max(results.get(phrase, 0), 0.72)

    lowered = text.lower()
    for term in BUILT_IN_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", lowered):
            results[term] = 0.95

    return [
        {"source_term": term, "target_term": None, "confidence": confidence}
        for term, confidence in sorted(results.items(), key=lambda item: (item[0]))[:limit]
    ]


def google_translate(text: str, target_language: str, source_language: str = "en") -> str | None:
    text = _clean_text(text)
    if not text:
        return None
    url = "https://translate.googleapis.com/translate_a/single?" + urlencode({
        "client": "gtx",
        "sl": source_language,
        "tl": target_language,
        "dt": "t",
        "q": text,
    })
    try:
        res = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        res.raise_for_status()
        data = res.json()
        translated = "".join(part[0] for part in data[0] if part and part[0])
        return _clean_text(translated)
    except Exception:
        return None


def offline_mock_translation(source_text: str, target_language: str, glossary: list[dict] | None = None) -> str:
    glossary = glossary or []

    if target_language != "cs":
        return source_text

    text = source_text
    glossary_pairs = [
        (str(item.get("source_term") or ""), str(item.get("target_term") or ""))
        for item in glossary
        if item.get("source_term") and item.get("target_term")
    ]

    dictionary = {
        "root collar": "kořenový krček",
        "planting pit": "výsadbová jáma",
        "root ball": "kořenový bal",
        "root system": "kořenový systém",
        "structural roots": "kosterní kořeny",
        "fine roots": "jemné kořeny",
        "stem": "kmen",
        "trunk": "kmen",
        "tree": "strom",
        "trees": "stromy",
        "must": "musí",
        "should": "má",
        "can": "může",
        "and": "a",
        "or": "nebo",
        "with": "s",
        "without": "bez",
    }

    pairs = glossary_pairs + list(dictionary.items())
    for src, tgt in sorted(pairs, key=lambda x: len(x[0]), reverse=True):
        if not src or not tgt:
            continue
        text = re.sub(rf"\b{re.escape(src)}\b", tgt, text, flags=re.IGNORECASE)

    text = text.replace("accura- te", "přesné").replace("unpru- ned", "bez řezu")
    return _clean_text(text)


def suggest_translation(source_text: str, target_language: str, context_before: str = "", context_after: str = "", glossary: list[dict] | None = None):
    api_key = os.getenv("OPENAI_API_KEY")
    lang = LANGUAGE_NAMES.get(target_language, target_language)
    glossary = glossary or []

    if not api_key:
        translated = google_translate(source_text, target_language, "en")
        if translated:
            return {
                "suggested_translation": translated,
                "confidence": 0.62,
                "notes": [
                    "Suggestion generated using the free Google Translate web endpoint. Review manually before approval.",
                    "For production reliability, set OPENAI_API_KEY or use an official translation API."
                ],
            }
        mock = offline_mock_translation(source_text, target_language, glossary)
        return {
            "suggested_translation": mock,
            "confidence": 0.25,
            "notes": [
                "Online translation fallback was unavailable; local fallback was used.",
                "Review manually before approval."
            ],
        }

    glossary_lines = "\n".join(
        f"- {item.get('source_term')}: {item.get('target_term')}" for item in glossary if item.get("target_term")
    )
    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    system = (
        "You are a professional translator of European arboricultural technical standards. "
        "Translate faithfully, preserve technical modality (must/should/can), and use approved terminology. "
        "Return only the translated segment, no commentary."
    )
    user = (
        f"Target language: {lang}\n\n"
        f"Approved glossary:\n{glossary_lines or '(none)'}\n\n"
        f"Previous context:\n{context_before}\n\n"
        f"Text to translate:\n{source_text}\n\n"
        f"Following context:\n{context_after}"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
    )
    return {
        "suggested_translation": response.choices[0].message.content.strip(),
        "confidence": 0.75,
        "notes": ["AI suggestion generated. A human translator/reviewer must approve it."],
    }


def translate_term(source_term: str, target_language: str) -> str | None:
    built = BUILT_IN_TERMS.get(source_term.lower(), {}).get(target_language)
    if built:
        return built
    return google_translate(source_term, target_language, "en")


def extract_candidate_terms(source_text: str, target_language: str) -> list[dict]:
    candidates: dict[str, float] = {}
    lowered = _clean_text(source_text).lower()

    for term in BUILT_IN_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", lowered):
            candidates[term] = 0.95

    for item in extract_adjective_noun_terms(source_text):
        candidates.setdefault(item["source_term"], item.get("confidence", 0.7))

    result = []
    for term, confidence in sorted(candidates.items(), key=lambda item: item[0])[:40]:
        result.append({
            "source_term": term,
            "target_term": BUILT_IN_TERMS.get(term, {}).get(target_language),
            "confidence": confidence,
        })
    return result
