---
inclusion: always
---

# Testing Strategy

This document defines the testing approach for Censorr, emphasizing test-first development and realistic integration testing.

## Test-First Development (TDD)

### Red-Green-Refactor Cycle
1. **Red**: Write a failing test that defines desired behavior
2. **Green**: Write minimal code to make the test pass
3. **Refactor**: Improve code while keeping tests green

### Commit Order
Commits must show tests preceding implementation:
1. First commit: Add failing test
2. Second commit: Implement feature to pass test
3. Optional: Refactor commits with tests still passing

### No Implementation Without Tests
- Every feature must have tests written first
- Tests must fail before implementation
- Implementation must make tests pass
- No code merged without corresponding tests

## Test Types and Priority

### Test Order (Priority)
1. **Contract Tests** - Verify public interfaces and contracts
2. **Integration Tests** - Test component interactions
3. **End-to-End Tests** - Validate complete workflows
4. **Unit Tests** - Test individual functions/classes

### Contract Tests
Test public interfaces and API contracts.

**When to write:**
- New public API endpoints
- CLI command interfaces
- Library public methods
- Data format contracts (JSON, YAML schemas)

**Example:**
```python
def test_webhook_post_accepts_valid_payload():
    """Contract: POST /webhook accepts Radarr payload with censorr_preset tag"""
    response = client.post('/webhook', json={
        'source': 'radarr',
        'eventType': 'Download',
        'tags': {'censorr_preset': 'movies'},
        'mediaPaths': ['/data/media/movies/Movie.mkv']
    })
    assert response.status_code == 202
    assert response.json()['status'] == 'accepted'
```

### Integration Tests
Test interactions between components using real dependencies.

**When to write:**
- Multi-component workflows
- External tool integration (FFmpeg, Docker)
- File system operations
- Queue/worker interactions

**Prefer real dependencies:**
- Use real Docker socket (not mocked)
- Use real file system (temp directories)
- Use real subprocess calls
- Mock only for failure injection

**Example:**
```python
def test_subtitle_extraction_with_real_ffmpeg(tmp_path):
    """Integration: Extract subtitles using real FFmpeg"""
    video_path = fixtures / 'sample.mkv'
    output_dir = tmp_path / 'output'
    
    result = extract_subtitles(video_path, output_dir, language='en')
    
    assert result.success
    assert (output_dir / 'sample.en.srt').exists()
    # Verify actual subtitle content
    content = (output_dir / 'sample.en.srt').read_text()
    assert 'WEBVTT' in content or '1\n00:00:' in content
```

### End-to-End Tests
Validate complete user workflows from start to finish.

**When to write:**
- Complete pipeline execution
- CLI command workflows
- Preset-based processing
- Multi-step operations

**Example:**
```python
def test_movies_preset_full_pipeline(tmp_path, sample_movie):
    """E2E: Process movie with movies preset"""
    output_dir = tmp_path / 'output'
    
    result = run_cli([
        'process', str(sample_movie),
        '--preset', 'movies',
        '--output', str(output_dir)
    ])
    
    assert result.returncode == 0
    # Verify all expected outputs
    assert (output_dir / 'Movie (2024) {edition-Censorr}.mkv').exists()
    assert (output_dir / 'Movie (2024).en.censorr.srt').exists()
```

### Unit Tests
Test individual functions and classes in isolation.

**When to write:**
- Complex algorithms (fuzzy matching, profanity detection)
- Data transformations
- Validation logic
- Edge cases and error handling

**Use mocks sparingly:**
- Only mock external dependencies when necessary
- Prefer dependency injection over mocking
- Document why mocking is needed

**Example:**
```python
def test_fuzzy_matcher_detects_variants():
    """Unit: Fuzzy matcher catches spelling variations"""
    matcher = FuzzyMatcher(threshold=85, terms=['damn'])
    
    assert matcher.matches('damn')
    assert matcher.matches('dammit')
    assert matcher.matches('god damn')
    assert not matcher.matches('damage')  # False positive check
```

## Realistic Integration Testing

### Use Real Dependencies
Prefer real dependencies over mocks:

**Real Docker:**
```python
@pytest.fixture
def docker_client():
    """Use real Docker client for integration tests"""
    return docker.from_env()

def test_container_deployment(docker_client, tmp_path):
    """Integration: Deploy container with real Docker"""
    container = docker_client.containers.run(
        'censorr:test',
        volumes={str(tmp_path): {'bind': '/data', 'mode': 'rw'}},
        detach=True
    )
    try:
        # Test real container behavior
        assert container.status == 'running'
    finally:
        container.remove(force=True)
```

**Real File System:**
```python
def test_sidecar_creation(tmp_path):
    """Integration: Create sidecar file on real filesystem"""
    video = tmp_path / 'Movie.mkv'
    video.touch()
    
    create_sidecar(video, language='en', tag='censorr')
    
    sidecar = tmp_path / 'Movie.en.censorr.srt'
    assert sidecar.exists()
    assert sidecar.stat().st_mode & 0o644  # Check permissions
```

### When to Mock
Mock only for:
- Failure injection (network errors, disk full)
- External services not available in CI
- Expensive operations in unit tests
- Non-deterministic behavior isolation

**Example of justified mocking:**
```python
def test_handles_ffmpeg_failure(mocker):
    """Unit: Handle FFmpeg failure gracefully"""
    mock_run = mocker.patch('subprocess.run')
    mock_run.side_effect = subprocess.CalledProcessError(1, 'ffmpeg')
    
    with pytest.raises(FFmpegError) as exc:
        extract_audio(video_path, output_dir)
    
    assert 'FFmpeg failed' in str(exc.value)
    assert exc.value.exit_code == 1
```

## Test Organization

### Directory Structure
```
tests/
├── contract/          # API/interface contract tests
│   ├── test_webhook_api.py
│   └── test_cli_interface.py
├── integration/       # Multi-component integration tests
│   ├── test_pipeline_flow.py
│   └── test_docker_deployment.py
├── e2e/              # End-to-end workflow tests
│   ├── test_movies_preset.py
│   └── test_tv_preset.py
└── unit/             # Isolated unit tests
    ├── test_fuzzy_matcher.py
    └── test_profanity_detector.py
```

### Fixtures and Test Data
```
tests/
├── fixtures/         # Test data and sample files
│   ├── sample.mkv    # Small test video
│   ├── sample.srt    # Sample subtitles
│   └── profanity.json
└── conftest.py       # Shared fixtures
```

## Test Quality Standards

### Test Naming
Use descriptive names that explain what is being tested:
```python
# Good
def test_fuzzy_matcher_detects_spelling_variations()
def test_webhook_rejects_missing_preset_tag()
def test_remux_preserves_original_audio_codec()

# Bad
def test_matcher()
def test_webhook()
def test_remux()
```

### Test Independence
Each test should be independent:
- No shared state between tests
- Use fixtures for setup/teardown
- Clean up resources (temp files, containers)
- Tests can run in any order

### Test Coverage Goals
- Contract tests: 100% of public interfaces
- Integration tests: All critical workflows
- E2E tests: All user-facing features
- Unit tests: Complex logic and edge cases

### Test Performance
- Unit tests: < 100ms each
- Integration tests: < 5s each
- E2E tests: < 30s each
- Use `pytest-timeout` to catch hanging tests

## CI/CD Integration

### Pre-commit Checks
Run before committing:
```bash
pytest tests/unit/          # Fast unit tests
pytest tests/contract/      # Contract tests
```

### CI Pipeline
Run on every PR:
```bash
pytest tests/              # All tests
pytest --cov=src/         # With coverage
pytest --slow             # Including slow integration tests
```

### Test Markers
Use pytest markers to categorize tests:
```python
@pytest.mark.unit
def test_fast_unit_test():
    pass

@pytest.mark.integration
def test_integration_with_docker():
    pass

@pytest.mark.slow
def test_full_pipeline_e2e():
    pass
```

## Documentation Testing

### Doctest for Examples
Use doctest for documentation examples:
```python
def mask_profanity(text: str, policy: str = 'partial') -> str:
    """
    Mask profane words in text.
    
    >>> mask_profanity('This is damn good')
    'This is d*** good'
    >>> mask_profanity('This is damn good', policy='full')
    'This is **** good'
    """
    pass
```

### Quickstart Validation
Validate quickstart examples in CI:
```bash
# Extract and run commands from quickstart.md
pytest --doctest-glob="*.md" docs/
```

---

**Version:** 0.5.0 | **Last Updated:** 2025-11-02
