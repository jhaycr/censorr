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


class TestFalsePositivePrevention:
    """Test comprehensive false positive prevention."""
    
    def test_shit_false_positives(self):
        """Test that 'shit' doesn't match innocent words."""
        profanity_terms = [
            ProfanityTerm(word="shit", fuzzy_threshold=95, variant_strategy="aggressive")
        ]
        matcher = FuzzyMatcher(similarity_threshold=85, allow_list=profanity_terms)
        
        # These should NOT be caught (false positives)
        false_positives = [
            "shirt", "shirts", "shirted", "shirting",  # shirt variants
            "sit", "sits", "sitting", "sat",           # sit variants  
            "shift", "shifts", "shifted", "shifting",   # shift variants
            "shot", "shots", "shooting",               # shot variants
            "shut", "shuts", "shutting",               # shut variants
            "shy", "shyly", "shyness",                 # shy variants
            "ship", "ships", "shipped", "shipping",    # ship variants
            "shop", "shops", "shopped", "shopping",    # shop variants
            "show", "shows", "showed", "showing",      # show variants
            "short", "shorter", "shortest", "shortly", # short variants
        ]
        
        for word in false_positives:
            assert not matcher.contains_profanity(word), f"'{word}' should NOT be caught as profanity"
        
        # These SHOULD be caught (legitimate profanity)
        legitimate_profanity = [
            "shit", "shits", "shitting", "shitted",   # exact and morphological
            "shitty", "shittier", "shittiest",        # aggressive variants
            "bullshit", "horseshit", "apeshit",       # compound forms
            "shithead", "shithole", "shitshow",       # compound forms
        ]
        
        for word in legitimate_profanity:
            assert matcher.contains_profanity(word), f"'{word}' should be caught as profanity"
    
    def test_fuck_false_positives(self):
        """Test that 'fuck' doesn't match innocent words."""
        profanity_terms = [
            ProfanityTerm(word="fuck", fuzzy_threshold=75, variant_strategy="aggressive")
        ]
        matcher = FuzzyMatcher(similarity_threshold=85, allow_list=profanity_terms)
        
        # These should NOT be caught (false positives)
        false_positives = [
            "duck", "ducks", "ducking",                # duck variants
            "tuck", "tucks", "tucked", "tucking",      # tuck variants
            "luck", "lucky", "luckily", "unlucky",     # luck variants  
            "suck", "sucks", "sucked", "sucking",      # suck variants
            "buck", "bucks", "bucking",                # buck variants
            "muck", "mucks", "mucked", "mucking",      # muck variants
            "stuck", "sticking",                       # stuck variants
            "truck", "trucks", "trucking",             # truck variants
            "pluck", "plucks", "plucked", "plucking",  # pluck variants
        ]
        
        for word in false_positives:
            assert not matcher.contains_profanity(word), f"'{word}' should NOT be caught as profanity"
        
        # These SHOULD be caught (legitimate profanity)
        legitimate_profanity = [
            "fuck", "fucks", "fucking", "fucked",     # exact and morphological
            "fucker", "fuckers",                      # morphological
            "fuckable", "fuckery", "fucktard",        # aggressive variants
            "motherfucker", "clusterfuck",            # compound forms
            "unfuckingbelievable",                    # embedded forms
        ]
        
        for word in legitimate_profanity:
            assert matcher.contains_profanity(word), f"'{word}' should be caught as profanity"
    
    def test_dick_false_positives(self):
        """Test that 'dick' doesn't match innocent words."""
        profanity_terms = [
            ProfanityTerm(word="dick", variant_strategy="aggressive")
        ]
        matcher = FuzzyMatcher(similarity_threshold=85, allow_list=profanity_terms)
        
        # These should NOT be caught (false positives)
        false_positives = [
            "deck", "decks", "decked", "decking",      # deck variants
            "sick", "sicker", "sickest", "sickly",     # sick variants
            "pick", "picks", "picked", "picking",      # pick variants
            "kick", "kicks", "kicked", "kicking",      # kick variants
            "tick", "ticks", "ticked", "ticking",      # tick variants
            "thick", "thicker", "thickest",            # thick variants
            "quick", "quicker", "quickest", "quickly", # quick variants
            "click", "clicks", "clicked", "clicking",  # click variants
            "stick", "sticks", "sticked", "sticking",  # stick variants
            "brick", "bricks",                         # brick variants
        ]
        
        for word in false_positives:
            assert not matcher.contains_profanity(word), f"'{word}' should NOT be caught as profanity"
        
        # These SHOULD be caught (legitimate profanity)
        legitimate_profanity = [
            "dick", "dicks",                          # exact and morphological
            "dickhead", "dickheads",                  # aggressive variants
            "dickwad", "dickish", "dickery",          # aggressive variants
        ]
        
        for word in legitimate_profanity:
            assert matcher.contains_profanity(word), f"'{word}' should be caught as profanity"
    
    def test_cunt_false_positives(self):
        """Test that 'cunt' doesn't match innocent words."""
        profanity_terms = [
            ProfanityTerm(word="cunt")  # Using default settings
        ]
        matcher = FuzzyMatcher(similarity_threshold=85, allow_list=profanity_terms)
        
        # These should NOT be caught (false positives)
        false_positives = [
            "cant", "cannot",                          # can't variants
            "hunt", "hunts", "hunted", "hunting",      # hunt variants
            "punt", "punts", "punted", "punting",      # punt variants
            "bunt", "bunts", "bunted", "bunting",      # bunt variants
            "runt", "runts",                           # runt variants
            "blunt", "blunts", "blunted", "blunting",  # blunt variants
            "grunt", "grunts", "grunted", "grunting",  # grunt variants
            "count", "counts", "counted", "counting",  # count variants
            "mount", "mounts", "mounted", "mounting",  # mount variants
            "front", "fronts", "fronted", "fronting",  # front variants
        ]
        
        for word in false_positives:
            assert not matcher.contains_profanity(word), f"'{word}' should NOT be caught as profanity"
        
        # This SHOULD be caught (legitimate profanity)
        assert matcher.contains_profanity("cunt"), "'cunt' should be caught as profanity"
    
    def test_bitch_false_positives(self):
        """Test that 'bitch' doesn't match innocent words."""
        profanity_terms = [
            ProfanityTerm(word="bitch", variant_strategy="aggressive")
        ]
        matcher = FuzzyMatcher(similarity_threshold=85, allow_list=profanity_terms)
        
        # These should NOT be caught (false positives)
        false_positives = [
            "batch", "batches", "batched", "batching", # batch variants
            "catch", "catches", "caught", "catching",  # catch variants
            "patch", "patches", "patched", "patching", # patch variants
            "match", "matches", "matched", "matching", # match variants
            "watch", "watches", "watched", "watching", # watch variants
            "hatch", "hatches", "hatched", "hatching", # hatch variants
            "latch", "latches", "latched", "latching", # latch variants
            "witch", "witches",                        # witch variants
            "switch", "switches", "switched", "switching", # switch variants
            "pitch", "pitches", "pitched", "pitching", # pitch variants
        ]
        
        for word in false_positives:
            assert not matcher.contains_profanity(word), f"'{word}' should NOT be caught as profanity"
        
        # These SHOULD be caught (legitimate profanity)
        legitimate_profanity = [
            "bitch", "bitches",                       # exact and morphological
            "bitchy", "bitching", "bitchiest",        # aggressive variants
            "bitchass",                               # compound forms
        ]
        
        for word in legitimate_profanity:
            assert matcher.contains_profanity(word), f"'{word}' should be caught as profanity"
    
    def test_optimized_list_false_positives(self):
        """Test false positives with the optimized profanity list."""
        # Load the optimized list
        import json
        import os
        
        config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'profanity_list_optimized.json')
        with open(config_path, 'r') as f:
            optimized_list = json.load(f)
        
        profanity_terms = normalize_profanity_list(optimized_list)
        matcher = FuzzyMatcher(similarity_threshold=85, allow_list=profanity_terms)
        
        # Comprehensive false positive test suite
        false_positives = [
            # Shit false positives
            "shirt", "shirts", "sit", "sits", "sitting", "shift", "shifts", "shot", "shots", "shut", "shuts",
            "ship", "ships", "shop", "shops", "show", "shows", "short", "shorter", "shy", "shyly",
            
            # Fuck false positives  
            "duck", "ducks", "tuck", "tucks", "luck", "lucky", "suck", "sucks", "buck", "bucks",
            "stuck", "truck", "trucks", "pluck", "plucks", "muck", "mucks",
            
            # Dick false positives
            "deck", "decks", "sick", "sicker", "pick", "picks", "kick", "kicks", "tick", "ticks",
            "thick", "thicker", "quick", "quicker", "click", "clicks", "stick", "sticks", "brick", "bricks",
            
            # Cunt false positives
            "cant", "cannot", "hunt", "hunts", "punt", "punts", "bunt", "bunts", "runt", "runts",
            "blunt", "blunts", "grunt", "grunts", "count", "counts", "mount", "mounts", "front", "fronts",
            
            # Bitch false positives
            "batch", "batches", "catch", "catches", "patch", "patches", "match", "matches", "watch", "watches",
            "hatch", "hatches", "latch", "latches", "witch", "witches", "switch", "switches", "pitch", "pitches",
            
            # Additional common words that might trigger false positives
            "sheet", "shell", "should", "class", "glass", "grass", "press", "dress", "stress",
            "black", "track", "crack", "stack", "attack", "pack", "back", "lack", "rack",
        ]
        
        failed_words = []
        for word in false_positives:
            if matcher.contains_profanity(word):
                failed_words.append(word)
        
        assert len(failed_words) == 0, f"These innocent words were incorrectly flagged as profanity: {failed_words}"
        
        # Test that legitimate profanity is still caught
        legitimate_profanity = [
            "shit", "fuck", "dick", "cunt", "bitch",  # Base terms
            "bullshit", "fuckface", "dickhead", "bitchy",  # Variants
            "goddamn", "jesus", "christ",  # Religious terms
        ]
        
        missed_words = []
        for word in legitimate_profanity:
            if not matcher.contains_profanity(word):
                missed_words.append(word)
        
        assert len(missed_words) == 0, f"These profane words were incorrectly missed: {missed_words}"