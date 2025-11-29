#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vocabulary Dictionary Server for IVO
Provides Korean and English dictionary lookups via stdin/stdout JSON protocol.
"""

import sys
import os
import io
import json
import requests
import xml.etree.ElementTree as ET
from pathlib import Path

# Fix Windows encoding issues
if sys.platform == 'win32':
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Load API key from .env file
def load_env():
    """Load environment variables from .env file."""
    env_path = Path(__file__).parent.parent.parent / '.env'
    env_vars = {}

    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()

    return env_vars

ENV = load_env()
KOREAN_DICT_API_KEY = ENV.get('KOREAN_DICT_API_KEY', '')
KOREAN_DICT_URL = "https://krdict.korean.go.kr/api/search"
EN_DICT_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/"


def send_message(msg: dict):
    """Send JSON message to stdout."""
    print(json.dumps(msg, ensure_ascii=False), flush=True)


def detect_lang(text: str) -> str:
    """
    Detect language of input text.
    Returns 'ko' for Korean, 'en' for English, 'unknown' otherwise.
    """
    hangul_count = 0
    latin_count = 0

    for ch in text:
        if '\uAC00' <= ch <= '\uD7A3':  # Korean syllables
            hangul_count += 1
        elif ('A' <= ch <= 'Z') or ('a' <= ch <= 'z'):
            latin_count += 1

    if hangul_count > 0 and latin_count == 0:
        return "ko"
    if latin_count > 0 and hangul_count == 0:
        return "en"
    if hangul_count > 0 and latin_count > 0:
        return "ko" if hangul_count >= latin_count else "en"

    return "unknown"


def get_english_definitions(word: str) -> dict:
    """
    Get English word definitions from Free Dictionary API.
    Returns dict with headword and definitions list.
    """
    url = EN_DICT_URL + word

    try:
        resp = requests.get(url, timeout=5)
    except requests.RequestException as e:
        return {"error": f"Request failed: {e}"}

    if resp.status_code != 200:
        return {"error": f"Word not found: {word}"}

    try:
        data = resp.json()
    except ValueError:
        return {"error": "Invalid response"}

    if not data:
        return {"error": "No data returned"}

    first_entry = data[0]
    headword = first_entry.get("word", word)

    definitions = []
    for meaning in first_entry.get("meanings", []):
        pos = meaning.get("partOfSpeech", "")
        for d in meaning.get("definitions", []):
            definition_text = d.get("definition", "")
            if definition_text:
                if pos:
                    definitions.append(f"[{pos}] {definition_text}")
                else:
                    definitions.append(definition_text)

    if not definitions:
        return {"error": "No definitions found"}

    return {
        "headword": headword,
        "definitions": definitions,
        "lang": "en"
    }


def get_korean_definitions(word: str) -> dict:
    """
    Get Korean word definitions from Korean Dictionary API.
    Returns dict with headword and definitions list.
    """
    if not KOREAN_DICT_API_KEY:
        return {"error": "Korean dictionary API key not configured"}

    params = {
        "key": KOREAN_DICT_API_KEY,
        "q": word,
        "part": "word",
        "sort": "dict",
        "num": 10,
    }

    try:
        resp = requests.get(KOREAN_DICT_URL, params=params, timeout=5)
    except requests.RequestException as e:
        return {"error": f"Request failed: {e}"}

    if resp.status_code != 200:
        return {"error": f"HTTP error: {resp.status_code}"}

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        return {"error": f"XML parse error: {e}"}

    if root.tag == "error":
        error_code = root.findtext("error_code")
        message = root.findtext("message")
        return {"error": f"API error ({error_code}): {message}"}

    items = root.findall("item")
    if not items:
        return {"error": f"Word not found: {word}"}

    first_item = items[0]
    headword = first_item.findtext("word") or word

    definitions = []
    for sense in first_item.findall("sense"):
        definition_text = sense.findtext("definition")
        if definition_text:
            definitions.append(definition_text.strip())

    if not definitions:
        return {"error": "No definitions found"}

    return {
        "headword": headword,
        "definitions": definitions,
        "lang": "ko"
    }


def clean_word(text: str) -> str:
    """
    Clean word by removing punctuation and symbols.
    Keeps only letters (Korean, English, etc.) and numbers.
    """
    import re
    # Remove leading/trailing punctuation and whitespace
    text = text.strip()
    # Remove common punctuation marks from both ends
    text = re.sub(r'^[^\w가-힣]+|[^\w가-힣]+$', '', text)
    # Remove any remaining non-word characters except hyphens in the middle
    # But keep the word intact
    return text.strip()


# Korean particles and endings to remove
KOREAN_PARTICLES = [
    # 조사 (particles)
    '은', '는', '이', '가', '을', '를', '의', '에', '에서', '에게', '한테', '께',
    '으로', '로', '와', '과', '랑', '이랑', '하고', '도', '만', '부터', '까지',
    '마다', '밖에', '처럼', '같이', '보다', '라고', '이라고', '고', '며', '으며',
    # 어미 (endings)
    '다', '요', '습니다', '입니다', 'ㅂ니다', '세요', '십시오', '구나', '네', '군',
    '지', '니', '나', '냐', '래', '자', '며', '고', '서', '면', '니까', '으니까',
    '어서', '아서', '려고', '으려고', '면서', '으면서', '지만', '는데', '은데', 'ㄴ데',
    '었', '았', '겠', '했', '된', '인', '적', '들',
]

def extract_korean_stem(word: str) -> str:
    """
    Extract Korean word stem by removing common particles and endings.
    """
    if not word:
        return word

    # Check if the word contains Korean characters
    has_korean = any('가' <= ch <= '힣' for ch in word)
    if not has_korean:
        return word

    original = word

    # Sort particles by length (longest first) to match longer patterns first
    sorted_particles = sorted(KOREAN_PARTICLES, key=len, reverse=True)

    # Try removing particles from the end
    for particle in sorted_particles:
        if word.endswith(particle) and len(word) > len(particle):
            candidate = word[:-len(particle)]
            # Make sure we have at least one character left
            if len(candidate) >= 1:
                word = candidate
                break

    # If the word is too short after removal, return original
    if len(word) < 1:
        return original

    return word


def lookup_single_word(word: str) -> dict:
    """
    Look up a single word, auto-detecting the language.
    For Korean, tries original word first, then tries with particles removed.
    """
    word = clean_word(word)
    if not word:
        return None

    lang = detect_lang(word)

    if lang == "en":
        result = get_english_definitions(word)
        if "error" not in result:
            return result
    elif lang == "ko":
        # Try original word first
        result = get_korean_definitions(word)
        if "error" not in result:
            return result

        # Try with particles/endings removed
        stem = extract_korean_stem(word)
        if stem != word:
            result = get_korean_definitions(stem)
            if "error" not in result:
                return result

    return None


def lookup_word(text: str) -> dict:
    """
    Look up words in text. Splits by spaces and finds definitions for each word.
    Skips words that are not found in dictionary.
    """
    text = text.strip()
    if not text:
        return {"error": "Empty text"}

    # Split by whitespace
    words = text.split()

    # Collect results for all words that have definitions
    all_results = []

    for word in words:
        result = lookup_single_word(word)
        if result:
            all_results.append({
                "word": clean_word(word),
                "headword": result.get("headword", clean_word(word)),
                "definitions": result.get("definitions", []),
                "lang": result.get("lang", "")
            })

    if not all_results:
        return {"error": "No definitions found for any word"}

    # Return combined results
    return {
        "results": all_results,
        "count": len(all_results)
    }


def main():
    """Main entry point - reads commands from stdin."""
    send_message({"type": "ready"})

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            line = line.strip()
            if not line:
                continue

            try:
                cmd = json.loads(line)
            except json.JSONDecodeError as e:
                send_message({"type": "error", "error": f"Invalid JSON: {e}"})
                continue

            cmd_type = cmd.get("type", "")

            if cmd_type == "lookup":
                text = cmd.get("word", "")
                result = lookup_word(text)

                if "error" in result:
                    send_message({
                        "type": "definition",
                        "word": text,
                        "error": result["error"]
                    })
                else:
                    # Multiple word results
                    send_message({
                        "type": "definition",
                        "word": text,
                        "results": result["results"],
                        "count": result["count"]
                    })

            elif cmd_type == "ping":
                send_message({"type": "pong"})

            elif cmd_type == "quit":
                break

            else:
                send_message({"type": "error", "error": f"Unknown command: {cmd_type}"})

        except KeyboardInterrupt:
            break
        except Exception as e:
            send_message({"type": "error", "error": str(e)})

    send_message({"type": "shutdown"})


if __name__ == "__main__":
    main()
