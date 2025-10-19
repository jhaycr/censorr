"""Test per-word fuzzy threshold and aggressive variant detection."""
import pytest
from src.models.profanity import ProfanityTerm, normalize_profanity_list
from src.utils.fuzzy_matcher import FuzzyMatcher


class TestPerWordFuzzyThreshold:
    """Test per-word fuzzy threshold configuration."""
    
    def test_normalize_profanity_list_strings(self):
        """Test normalization of string list to ProfanityTerm objects."""
        entries = ["fuck", "shit", "damn"]
        normalized = normalize_profanity_list(entries, 85.0)
        
        assert len(normalized) == 3
        assert all(isinstance(term, ProfanityTerm) for term in normalized)
        assert normalized[0].word == "fuck"
        assert normalized[0].get_effective_threshold(85.0) == 95.0  # Length-based minimum
        assert not normalized[0].is_aggressive_variant_enabled()
    
    def test_normalize_profanity_list_mixed(self):
        """Test normalization of mixed string/dict list."""
        entries = [
            "damn",
            {"word": "fuck", "fuzzy_threshold": 70, "variant_strategy": "aggressive"},
            {"word": "shit", "fuzzy_threshold": 95}
        ]
        normalized = normalize_profanity_list(entries, 85.0)
        
        assert len(normalized) == 3
        
        # String entry uses defaults but gets length-based minimum
        damn_term = next(term for term in normalized if term.word == "damn")
        assert damn_term.get_effective_threshold(85.0) == 95.0  # Length-based minimum for 4-char word
        assert not damn_term.is_aggressive_variant_enabled()
        
        # Custom threshold but length-based minimum applies
        fuck_term = next(term for term in normalized if term.word == "fuck")
        assert fuck_term.get_effective_threshold(85.0) == 95.0  # max(70, 95) due to length
        assert fuck_term.is_aggressive_variant_enabled()
        
        # Custom threshold already meets length-based minimum
        shit_term = next(term for term in normalized if term.word == "shit")
        assert shit_term.get_effective_threshold(85.0) == 95.0
        assert not shit_term.is_aggressive_variant_enabled()
    
    def test_length_based_thresholds(self):
        """Test length-based threshold rules."""
        # Short words (≤4 chars) get 95% minimum
        short_term = ProfanityTerm(word="shit", fuzzy_threshold=80)
        assert short_term.get_effective_threshold(85.0) == 95.0
        
        # Short words with high custom threshold keep it
        strict_short_term = ProfanityTerm(word="fuck", fuzzy_threshold=98)
        assert strict_short_term.get_effective_threshold(85.0) == 98.0
        
        # Long words use custom or global threshold
        long_term = ProfanityTerm(word="bullshit", fuzzy_threshold=70)
        assert long_term.get_effective_threshold(85.0) == 70.0
        
        # Long words without custom threshold use global
        long_default_term = ProfanityTerm(word="motherfucker")
        assert long_default_term.get_effective_threshold(85.0) == 85.0
    
    def test_shit_false_positive_fix(self):
        """Test that shit false positives are eliminated."""
        profanity_terms = [
            ProfanityTerm(word="shit", fuzzy_threshold=95, variant_strategy="aggressive")
        ]
        matcher = FuzzyMatcher(similarity_threshold=85, allow_list=profanity_terms)
        
        # False positives should be rejected
        assert not matcher.contains_profanity("shirt")   # 88.89% < 95%
        assert not matcher.contains_profanity("sit")     # 85.71% < 95%
        assert not matcher.contains_profanity("shift")   # 88.89% < 95%
        
        # Actual profanity should be caught
        assert matcher.contains_profanity("shit")        # 100% ≥ 95%
        assert matcher.contains_profanity("shits")       # Morphology rule
        assert matcher.contains_profanity("shitting")    # Morphology rule
        assert matcher.contains_profanity("shitty")      # Aggressive strategy
    
    def test_fuzzy_matcher_per_term_thresholds(self):
        """Test that FuzzyMatcher respects per-term thresholds."""
        profanity_terms = [
            ProfanityTerm(word="strict", fuzzy_threshold=95),  # Very strict
            ProfanityTerm(word="lenient", fuzzy_threshold=50), # Very lenient
            ProfanityTerm(word="default")  # Uses global default
        ]
        
        matcher = FuzzyMatcher(
            similarity_threshold=80.0,
            allow_list=profanity_terms
        )
        
        # Test per-term threshold access
        assert matcher._get_effective_threshold("strict") == 95
        assert matcher._get_effective_threshold("lenient") == 50
        assert matcher._get_effective_threshold("default") == 80.0
        assert matcher._get_effective_threshold("unknown") == 80.0  # Global default
    
    def test_aggressive_variant_detection(self):
        """Test aggressive variant detection for morphological forms."""
        profanity_terms = [
            ProfanityTerm(word="fuck", variant_strategy="aggressive"),
            ProfanityTerm(word="shit", variant_strategy="default")
        ]
        
        matcher = FuzzyMatcher(
            similarity_threshold=85.0,
            allow_list=profanity_terms
        )
        
        # Test aggressive vs default detection
        assert matcher._is_aggressive_enabled("fuck")
        assert not matcher._is_aggressive_enabled("shit")
        
        # Test aggressive morphology matching
        # Should match compound/embedded forms for "fuck" but not "shit"
        fuck_score = matcher._morphology_match_score("fuckable", "fuck")
        shit_score = matcher._morphology_match_score("shitable", "shit")
        
        # Aggressive mode should find "fuck" in "fuckable"
        assert fuck_score == 100.0
        
        # Default mode should NOT find "shit" in "shitable" (not a real morphological variant)
        assert shit_score < 100.0
    
    def test_compound_variant_detection(self):
        """Test aggressive detection of compound forms."""
        profanity_terms = [
            ProfanityTerm(word="fuck", variant_strategy="aggressive")
        ]
        
        matcher = FuzzyMatcher(
            similarity_threshold=85.0,
            allow_list=profanity_terms
        )
        
        # Test compound patterns
        test_cases = [
            ("unfuck", "fuck", 100.0),      # prefix compound
            ("fuckup", "fuck", 100.0),      # suffix compound
            ("refuck", "fuck", 100.0),      # prefix compound
            ("fuckward", "fuck", 100.0),    # suffix compound
            ("fuckable", "fuck", 100.0),    # morphological variant
            ("unfuckingbelievable", "fuck", 100.0),  # embedded compound
        ]
        
        for query, target, expected_score in test_cases:
            score = matcher._morphology_match_score(query, target)
            assert score == expected_score, f"Expected {query} -> {target} to score {expected_score}, got {score}"
    
    def test_backward_compatibility(self):
        """Test that legacy string lists still work."""
        legacy_list = ["fuck", "shit", "bullshit"]  # Include a long word
        
        matcher = FuzzyMatcher(
            similarity_threshold=85.0,
            allow_list=legacy_list
        )
        
        # Should work with legacy interface
        assert len(matcher.allow_list) == 3
        assert "fuck" in matcher.allow_list
        
        # Short words get length-based minimum threshold
        assert matcher._get_effective_threshold("fuck") == 95.0  # Length-based minimum
        assert matcher._get_effective_threshold("shit") == 95.0  # Length-based minimum
        
        # Long words use global threshold
        assert matcher._get_effective_threshold("bullshit") == 85.0  # Global threshold
        
        # Should not enable aggressive mode by default
        assert not matcher._is_aggressive_enabled("fuck")


class TestVariantDetectionIntegration:
    """Test variant detection in full text matching."""
    
    def test_catch_variants_not_in_list(self):
        """Test that aggressive mode catches variants not explicitly listed."""
        # Configure "fuck" with aggressive detection
        profanity_terms = [
            ProfanityTerm(word="fuck", variant_strategy="aggressive", fuzzy_threshold=85)
        ]
        
        matcher = FuzzyMatcher(
            similarity_threshold=85.0,
            allow_list=profanity_terms
        )
        
        # Test text with variants that should be caught
        test_text = "That's totally fuckable behavior, so unfucking believable!"
        matches = matcher.find_matches_in_text(test_text)
        
        # Should find both variants
        assert len(matches) >= 2
        matched_terms = {match.target for match in matches}
        assert "fuck" in matched_terms
        
        # Verify specific variants are matched
        matched_queries = {match.query for match in matches}
        assert "fuckable" in matched_queries or any("fuckable" in query for query in matched_queries)
        assert "unfucking" in matched_queries or any("unfucking" in query for query in matched_queries)
    
    def test_per_word_threshold_in_text(self):
        """Test that per-word thresholds work in text matching."""
        profanity_terms = [
            ProfanityTerm(word="lenient", fuzzy_threshold=50),  # Low threshold
            ProfanityTerm(word="strict", fuzzy_threshold=95),   # High threshold
        ]
        
        matcher = FuzzyMatcher(
            similarity_threshold=85.0,  # Global default
            allow_list=profanity_terms
        )
        
        # Test with slightly misspelled words
        lenient_matches = matcher.find_matches_in_text("lienient behavior")  # Typo, ~70% match
        strict_matches = matcher.find_matches_in_text("strikt behavior")     # Typo, ~70% match
        
        # "lenient" should match due to low threshold (50%)
        assert len(lenient_matches) > 0
        
        # "strict" should NOT match due to high threshold (95%)  
        assert len(strict_matches) == 0