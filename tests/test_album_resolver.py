"""
test_album_resolver.py
Unit tests for studio album heuristic resolution, primary artist extraction,
suspicious track filtering, and antagonistic keyword checks.
"""

from src.album_resolver import (
    get_primary_artist,
    is_studio_album,
    is_suspicious_match,
    FORBIDDEN_WORDS,
)


def test_get_primary_artist():
    assert get_primary_artist("Anther, Dib") == "Anther"
    assert get_primary_artist("3AM feat. Khea") == "3AM"
    assert get_primary_artist("Bizarrap ft. Quevedo") == "Bizarrap"
    assert get_primary_artist("Rosalía with The Weeknd") == "Rosalía"
    assert get_primary_artist("Mora / Bad Bunny / Sech") == "Mora"
    assert get_primary_artist("Duki") == "Duki"
    assert get_primary_artist("") == "Unknown Artist"
    assert get_primary_artist(None) == "Unknown Artist"


def test_is_studio_album():
    # Regular studio album
    assert is_studio_album("Donde Quiero Estar", "Columbia") is True
    assert is_studio_album("Un Verano Sin Ti", "Moscow Mule") is True

    # Standalone singles (album matches song title exactly)
    assert is_studio_album("Columbia", "Columbia") is False
    assert is_studio_album("columbia", "Columbia") is False

    # Single indicators in album name
    assert is_studio_album("Columbia - Single", "Columbia") is False
    assert is_studio_album("Playa Saturno (EP)", "Cosas Guapas") is False
    assert is_studio_album("Ella Remix Pack", "Ella") is False
    assert is_studio_album("Sencillo 2024", "Cancion") is False

    # Empty or null
    assert is_studio_album("", "Song") is False
    assert is_studio_album(None, "Song") is False


def test_is_suspicious_match():
    # Covers, karaoke, 8-bit, tributes
    assert is_suspicious_match("Coldplay", "Yellow", "Party Tyme Karaoke", "Yellow (Karaoke Version)") is True
    assert is_suspicious_match("Nirvana", "Smells Like Teen Spirit", "Sweet Little Band", "Smells Like Teen Spirit") is True
    assert is_suspicious_match("Adele", "Hello", "8-Bit Arcade", "Hello 8 bit") is True
    assert is_suspicious_match("Daft Punk", "Get Lucky", "Cover Band", "Get Lucky Cover") is True

    # Genuine match
    assert is_suspicious_match("Quevedo", "Columbia", "Quevedo", "Columbia") is False

    # Completely different artist
    assert is_suspicious_match("Bad Bunny", "Tití Me Preguntó", "Random DJ", "Tití Me Preguntó Remix") is True


def test_forbidden_words_constant():
    assert "cover" in FORBIDDEN_WORDS
    assert "karaoke" in FORBIDDEN_WORDS
    assert "8-bit" in FORBIDDEN_WORDS
    assert "speed up" in FORBIDDEN_WORDS
