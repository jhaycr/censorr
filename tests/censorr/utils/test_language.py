import pytest

from censorr.utils.language import is_language_match, normalize_languages


class TestNormalizeLanguages:
    """Test language normalization and expansion."""

    def test_expands_language_code_key(self):
        # 'en' is a key, should expand to all its variants
        result = normalize_languages(["en"])
        assert result == {"en", "eng", "english"}

    def test_expands_language_name(self):
        # 'English' is a variant value, should expand to full set
        result = normalize_languages(["English"])
        assert result == {"en", "eng", "english"}

    def test_expands_three_letter_code(self):
        # 'eng' is a variant value
        result = normalize_languages(["eng"])
        assert result == {"en", "eng", "english"}

    def test_case_insensitive(self):
        result1 = normalize_languages(["EN"])
        result2 = normalize_languages(["en"])
        assert result1 == result2

    def test_multiple_languages(self):
        result = normalize_languages(["en", "es", "fr"])
        assert "eng" in result
        assert "spa" in result
        assert "fra" in result

    def test_deduplicates_overlapping_variants(self):
        # Both 'en' and 'eng' refer to the same language
        result = normalize_languages(["en", "eng"])
        assert result == {"en", "eng", "english"}

    def test_unknown_language_added_as_is(self):
        result = normalize_languages(["unknown"])
        assert "unknown" in result

    def test_mixed_known_and_unknown(self):
        result = normalize_languages(["en", "unknown"])
        assert "eng" in result
        assert "english" in result
        assert "unknown" in result

    def test_empty_list(self):
        result = normalize_languages([])
        assert result == set()

    def test_all_major_languages(self):
        langs = ["en", "es", "fr", "de", "ja", "zh", "pt", "ru", "ar", "it"]
        result = normalize_languages(langs)
        # Should have many variants
        assert len(result) > 10
        assert "eng" in result
        assert "spa" in result
        assert "fra" in result


class TestIsLanguageMatch:
    """Test language matching against filter list."""

    def test_matches_language_code(self):
        assert is_language_match("eng", ["en"])

    def test_matches_language_name(self):
        assert is_language_match("eng", ["English"])

    def test_matches_three_letter_code(self):
        assert is_language_match("eng", ["eng"])

    def test_no_match_different_language(self):
        assert not is_language_match("eng", ["es"])

    def test_no_match_empty_filter(self):
        assert not is_language_match("eng", [])

    def test_case_insensitive_match(self):
        assert is_language_match("ENG", ["en"])
        assert is_language_match("eng", ["EN"])

    def test_matches_first_filter_item(self):
        assert is_language_match("eng", ["en", "es"])

    def test_matches_second_filter_item(self):
        assert is_language_match("spa", ["en", "es"])

    def test_multiple_filter_variants(self):
        # Stream is 'eng', filter has variant names
        assert is_language_match("eng", ["English"])
        assert is_language_match("eng", ["english"])

    def test_stream_as_different_variant(self):
        # Stream code 'eng', filter code 'en' (both English)
        assert is_language_match("eng", ["en"])

    def test_no_match_for_unknown_stream_and_filter(self):
        # Unknown stream and filter don't match
        assert not is_language_match("unknown1", ["unknown2"])

    def test_match_when_both_unknown_and_same(self):
        # If both are unknown and identical, they match
        assert is_language_match("xyz", ["xyz"])

    def test_spanish_variants(self):
        assert is_language_match("spa", ["es"])
        assert is_language_match("spa", ["spanish"])
        assert is_language_match("es", ["spa"])

    def test_french_variants(self):
        assert is_language_match("fra", ["fr"])
        assert is_language_match("fra", ["french"])
        assert is_language_match("fr", ["fra"])

    def test_chinese_variants(self):
        assert is_language_match("zho", ["zh"])
        assert is_language_match("zh", ["zho"])

    def test_japanese_variants(self):
        assert is_language_match("jpn", ["ja"])
        assert is_language_match("ja", ["jpn"])

    def test_real_world_audio_stream(self):
        # Typical ffprobe audio stream language tag
        assert is_language_match("eng", ["en", "eng", "english"])

    def test_real_world_subtitle_stream(self):
        # Typical ffprobe subtitle stream with unknown language tag
        # "und" (undetermined) is not in any language map, so won't match specific filters
        assert not is_language_match("und", ["en"])
        assert not is_language_match("und", ["es"])
