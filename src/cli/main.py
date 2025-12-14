"""Main CLI entry point for censorr."""
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Set
import json

import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.models.selectors import Selector
from src.models.config import Config, OutputMode, DestinationPolicy, PresetConfig
from src.planner.planner import Planner
from src.planner.registry import OperationRegistry
from src.planner.executor import Executor

# Import all available operations
from src.ops.subtitle_extract import ExtractSubtitlesOperation
from src.ops.subtitle_merge import MergeSubtitlesOperation
from src.ops.subtitle_mask import MaskSubtitlesOperation
from src.ops.subtitle_export import SubtitleExportOperation
from src.ops.audio_extract import ExtractAudioOperation
from src.ops.audio_mute import MuteAudioOperation
from src.ops.audio_qc import AudioQualityCheckOperation
from src.ops.subtitle_qc import SubtitleQualityCheckOperation
from src.ops.video_remux import RemuxOperation

# Create the main CLI app
app = typer.Typer(
    name="censorr",
    help="CLI tool for censoring audio and subtitles in media files",
    add_completion=False,
)

console = Console()

def create_operation_registry() -> OperationRegistry:
    """Create and populate the operation registry with all available operations."""
    registry = OperationRegistry()
    
    # Register all operations
    registry.register(ExtractSubtitlesOperation())
    registry.register(MergeSubtitlesOperation())
    registry.register(MaskSubtitlesOperation())
    registry.register(SubtitleExportOperation())
    registry.register(ExtractAudioOperation())
    registry.register(MuteAudioOperation())
    registry.register(AudioQualityCheckOperation())
    registry.register(SubtitleQualityCheckOperation())
    registry.register(RemuxOperation())
    
    return registry

def determine_target_types(operation_list: Optional[List[str]], registry: OperationRegistry) -> Set[ArtifactType]:
    """Determine target artifact types from operation list or use defaults."""
    if operation_list:
        # If specific operations are requested, find what they produce
        target_types = set()
        for op_name in operation_list:
            try:
                operation = registry.get_operation(op_name)
                target_types.update(operation.produces)
            except KeyError:
                # Operation not found - let planner handle the error
                pass
        return target_types
    else:
        # Default: full pipeline ending with remuxed video
        return {ArtifactType.VIDEO}

# Version callback
def version_callback(value: bool):
    """Print version and exit."""
    if value:
        rprint("censorr version 0.1.0")
        raise typer.Exit()

# Available operations
AVAILABLE_OPERATIONS = [
    "subtitle_extract",
    "subtitle_merge", 
    "subtitle_mask",
    "subtitle_export",
    "audio_extract",
    "audio_mute",
    "audio_qc",
    "subtitle_qc",
    "video_remux"
]

OPERATION_DESCRIPTIONS = {
    "subtitle_extract": "Extract subtitle tracks from video files",
    "subtitle_merge": "Combine multiple subtitle files into one",
    "subtitle_mask": "Apply profanity filtering to subtitle content",
    "subtitle_export": "Create external subtitle/metadata files",
    "audio_extract": "Extract audio tracks from video files",
    "audio_mute": "Apply mute windows to audio tracks",
    "audio_qc": "Verify audio muting effectiveness through energy analysis",
    "subtitle_qc": "Verify subtitle masking effectiveness and detect residual profanity",
    "video_remux": "Combine processed tracks into final video"
}

@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", callback=version_callback, is_eager=True,
        help="Show version and exit"
    )
):
    """
    Censorr - CLI tool for censoring audio and subtitles in media files.
    
    Process media files to automatically detect and censor inappropriate content
    in both audio and subtitle tracks using configurable profanity detection.
    """
    pass


@app.command()
def process(
    input_file: str = typer.Argument(..., help="Input media file to process"),
    config: Optional[str] = typer.Option(
        None, "--config",
        help="Path to configuration file (default: config/censorr.json or ~/.config/censorr/config.json)"
    ),
    output: str = typer.Option(
        "./output", "--output", "-o",
        help="Output directory for processed files"
    ),
    operations: Optional[str] = typer.Option(
        None, "--operations", "--ops",
        help="Comma-separated list of operations to run (default: auto-detect)"
    ),
    language: Optional[str] = typer.Option(
        None, "--language", "-l",
        help="Filter by language code (e.g., 'en', 'es')"
    ),
    mute_windows: Optional[str] = typer.Option(
        None, "--mute-windows", "-m",
        help="Path to external mute windows JSON file"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n",
        help="Show what would be done without executing"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Enable verbose output"
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Overwrite existing output files"
    ),
    profanity_list_file: Optional[str] = typer.Option(
        None, "--profanity-list-file",
        help="Path to JSON file with an array of {word: string, ...} objects for profanity masking"
    ),
    create_subtitle_sidecar: bool = typer.Option(
        False, "--create-subtitle-sidecar",
        help="Create sidecar subtitle files alongside remuxed video"
    ),
    preset: Optional[str] = typer.Option(
        None, "--preset",
        help="Use a named preset configuration (e.g., 'movies', 'tv')"
    ),
    prune_non_clean_tracks: bool = typer.Option(
        False, "--prune-non-clean-tracks",
        help="Keep only muted audio and masked subtitles in the final remux"
    )
):
    """
    Process a media file through the censorr pipeline.
    
    Automatically extracts, processes, and remuxes audio and subtitle tracks
    to create a censored version of the input media file.
    """
    try:
        # Load configuration with fallback hierarchy
        try:
            app_config = Config.load_with_fallback(config)
            if verbose and config:
                rprint(f"[green]Loaded configuration from: {config}[/green]")
        except Exception as e:
            rprint(f"[yellow]Warning: Failed to load config: {e}[/yellow]")
            rprint("[yellow]Using default configuration[/yellow]")
            app_config = Config()
        
        # Resolve preset if specified
        preset_config = None
        if preset:
            if preset in app_config.presets:
                preset_config = app_config.presets[preset]
                if verbose:
                    rprint(f"[green]Using preset: {preset}[/green]")
            else:
                rprint(f"[red]Error: Preset '{preset}' not found in configuration[/red]")
                raise typer.Exit(1)
        
        # Smart defaults for removed CLI options
        # These values come from config/preset or intelligent defaults
        
        # Output and destination settings - smart defaults from config/preset
        effective_output_mode = None
        effective_dest_policy = None
        effective_dest_policy_tag = None
        effective_dest_separate_root = None
        effective_backup = False
        
        # Audio encoding - always preserve original (per user requirement)
        audio_transcode_to_original = False  # Don't transcode by default
        audio_target_codec = None  # Auto-detect from original
        audio_bitrate = None  # Always preserve original bitrate
        audio_channels = None  # Preserve original channel count
        
        # QC settings - intelligent defaults
        continue_on_qc_fail = False  # Conservative default
        continue_on_audio_qc_fail = False  # Conservative default
        audio_qc_threshold_db = -15.0  # Reasonable strictness
        audio_qc_control_window = 1.0  # 1 second control window
        
        # Execution settings - auto-detect based on system
        parallel = False  # Default to sequential for reliability
        jobs = 1  # Single job by default
        skip_existing = False  # Process by default
        
        # Subtitle filtering - sensible defaults
        subtitle_title_include = None
        subtitle_title_exclude = None
        subtitle_title_regex = None
        subtitle_mode = "masked_only"  # Default from config
        
        # File management - conservative defaults
        persist_intermediate = False  # Clean up by default
        final_dest = None  # No automatic moving
        track_index = None  # No track filtering
        strict_audio_parity = False  # Warn only by default
        fuzzy_threshold = None  # Use config default
        sidecar_tag = "censorr"  # Default tag
        
        if preset_config:
            # Apply preset output settings
            preset_output = preset_config.output
            if 'output_mode' in preset_output:
                effective_output_mode = preset_output['output_mode']
            if preset_config.backup_default:
                effective_backup = preset_config.backup_default
            
            # Apply preset destination policy if set
            if preset_config.destination_policy:
                policy_obj = preset_config.destination_policy
                effective_dest_policy = policy_obj.policy
                effective_dest_policy_tag = policy_obj.tag
                effective_dest_separate_root = policy_obj.separate_root
        
        # Apply config defaults if still not set
        if not effective_output_mode:
            effective_output_mode = app_config.output_mode.value
        if app_config.destination_policy and not effective_dest_policy:
            policy_obj = app_config.destination_policy
            effective_dest_policy = policy_obj.policy
            if not effective_dest_policy_tag:
                effective_dest_policy_tag = policy_obj.tag
            if not effective_dest_separate_root:
                effective_dest_separate_root = policy_obj.separate_root
        
        # Merge config with CLI arguments (CLI args take precedence)
        # For boolean flags, we need to detect if they were explicitly set or using default
        merged_args = app_config.merge_with_args(
            output=output if output != "./output" else None,  # Only override if not default
            dry_run=dry_run if dry_run else None,  # Only override if True
            verbose=verbose if verbose else None,  # Only override if True
            force=force if force else None,  # Only override if True
            language=language,
            profanity_list_file=profanity_list_file
        )
        
        # Use merged values for the rest of the function
        output = merged_args['output']
        dry_run = merged_args['dry_run']
        verbose = merged_args['verbose']
        force = merged_args['force']
        language = merged_args['language']
        profanity_list_file = merged_args['profanity_list_file']
        
        # Get additional values from config with smart defaults
        skip_existing = merged_args.get('skip_existing', app_config.skip_existing)
        parallel = merged_args.get('parallel', app_config.parallel)
        jobs = merged_args.get('jobs', app_config.jobs)
        continue_on_qc_fail = merged_args.get('continue_on_qc_fail', app_config.continue_on_qc_fail)
        continue_on_audio_qc_fail = merged_args.get('continue_on_audio_qc_fail', app_config.continue_on_audio_qc_fail)
        audio_qc_threshold_db = app_config.audio_qc_threshold_db
        audio_qc_control_window = app_config.audio_qc_control_window
        subtitle_mode = merged_args.get('subtitle_mode', app_config.subtitle_mode)
        sidecar_tag = merged_args.get('sidecar_tag', app_config.sidecar_tag)
        prune_non_clean_tracks = prune_non_clean_tracks or merged_args.get('prune_non_clean_tracks', app_config.prune_non_clean_tracks)
        strict_audio_parity = merged_args.get('strict_audio_parity', app_config.strict_audio_parity)
        fuzzy_threshold = merged_args.get('fuzzy_threshold', app_config.fuzzy_threshold)
        persist_intermediate = app_config.persist_intermediate
        final_dest = app_config.final_dest
        track_index = app_config.track_index
        
        # Apply config defaults for audio encoding (these preserve original by default)
        if not audio_transcode_to_original:
            audio_transcode_to_original = app_config.audio_transcode_to_original
        if not audio_target_codec:
            audio_target_codec = app_config.audio_target_codec
        if not audio_bitrate:
            audio_bitrate = app_config.audio_bitrate
        if not audio_channels:
            audio_channels = app_config.audio_channels
        
        # Initialize subtitle filter defaults from config
        subtitle_title_include = ','.join(app_config.subtitle_title_include) if app_config.subtitle_title_include else None
        subtitle_title_exclude = ','.join(app_config.subtitle_title_exclude) if app_config.subtitle_title_exclude else None
        subtitle_title_regex = ','.join(app_config.subtitle_title_regex) if app_config.subtitle_title_regex else None
        # Apply preset flag defaults when not set via CLI (CLI > preset > config)
        if preset_config and isinstance(preset_config.flags, dict):
            if not create_subtitle_sidecar and 'create_subtitle_sidecar' in preset_config.flags:
                create_subtitle_sidecar = bool(preset_config.flags['create_subtitle_sidecar'])
            if not profanity_list_file and 'profanity_list_file' in preset_config.flags:
                profanity_list_file = preset_config.flags['profanity_list_file']
            # Language default from preset flags
            if not language and 'language' in preset_config.flags:
                language = preset_config.flags['language']
            # Subtitle mode default from preset flags if not overridden on CLI
            if 'subtitle_mode' in preset_config.flags:
                # If CLI didn't change it (still default), honor preset
                if subtitle_mode == app_config.subtitle_mode:
                    subtitle_mode = preset_config.flags['subtitle_mode']
            
            # Apply preset defaults for removed CLI options (via smart defaults)
            if 'parallel' in preset_config.flags:
                parallel = bool(preset_config.flags['parallel'])
            if 'jobs' in preset_config.flags:
                try:
                    jobs = int(preset_config.flags['jobs'])
                except Exception:
                    pass
            if 'continue_on_qc_fail' in preset_config.flags:
                continue_on_qc_fail = bool(preset_config.flags['continue_on_qc_fail'])
            if 'continue_on_audio_qc_fail' in preset_config.flags:
                continue_on_audio_qc_fail = bool(preset_config.flags['continue_on_audio_qc_fail'])
            if 'audio_qc_threshold_db' in preset_config.flags:
                try:
                    audio_qc_threshold_db = float(preset_config.flags['audio_qc_threshold_db'])
                except Exception:
                    pass
            if 'audio_qc_control_window' in preset_config.flags:
                try:
                    audio_qc_control_window = float(preset_config.flags['audio_qc_control_window'])
                except Exception:
                    pass
            if 'subtitle_title_include' in preset_config.flags:
                subtitle_title_include = preset_config.flags['subtitle_title_include']
            if 'subtitle_title_exclude' in preset_config.flags:
                subtitle_title_exclude = preset_config.flags['subtitle_title_exclude']
            if 'subtitle_title_regex' in preset_config.flags:
                subtitle_title_regex = preset_config.flags['subtitle_title_regex']
            if 'prune_non_clean_tracks' in preset_config.flags:
                prune_non_clean_tracks = bool(preset_config.flags['prune_non_clean_tracks'])
        # Validate input file
        input_path = Path(input_file)
        if not input_path.exists():
            rprint(f"[red]Error: Input file '{input_file}' not found[/red]")
            raise typer.Exit(1)
        
        # Create output directory
        output_path = Path(output)
        if not output_path.exists():
            output_path.mkdir(parents=True, exist_ok=True)
            if verbose:
                rprint(f"[green]Created output directory: {output_path}[/green]")
        
        # Parse operations
        operation_list = None
        if operations:
            operation_list = [op.strip() for op in operations.split(",")]
            # Validate operations
            invalid_ops = [op for op in operation_list if op not in AVAILABLE_OPERATIONS]
            if invalid_ops:
                rprint(f"[red]Error: Invalid operations: {', '.join(invalid_ops)}[/red]")
                rprint(f"[yellow]Available operations: {', '.join(AVAILABLE_OPERATIONS)}[/yellow]")
                raise typer.Exit(1)
        elif preset_config and preset_config.operations:
            # If no CLI operations provided, use operations from the selected preset
            operation_list = preset_config.operations
            if verbose:
                rprint(f"[green]Using operations from preset '{preset}': {', '.join(operation_list)}[/green]")
        
        # Create selectors
        selectors = []
        
        # Parse title filter lists with smart defaults
        title_include_list = []
        if subtitle_title_include:
            title_include_list = [s.strip() for s in subtitle_title_include.split(",")]
        
        title_exclude_list = []
        if subtitle_title_exclude:
            title_exclude_list = [s.strip() for s in subtitle_title_exclude.split(",")]
        
        title_regex_list = []
        if subtitle_title_regex:
            title_regex_list = [s.strip() for s in subtitle_title_regex.split(",")]
        
        # Check if any subtitle filtering is requested
        has_subtitle_filters = (language or title_include_list or title_exclude_list or 
                               title_regex_list)
        
        if has_subtitle_filters:
            # Create subtitle selector
            subtitle_selector = Selector(
                type=ArtifactType.SUBTITLE,
                language=language,
                title_include=title_include_list,
                title_exclude=title_exclude_list,
                title_regex=title_regex_list
            )
            selectors.append(subtitle_selector)
        
        if language:
            # Create audio selector with same criteria
            audio_selector = Selector(
                type=ArtifactType.AUDIO,
                language=language
            )
            selectors.append(audio_selector)
        
        if track_index is not None:
            # Track index filtering not yet supported in Selector model
            rprint("[yellow]Warning: Track index filtering not yet implemented[/yellow]")
        
        # Create input artifact
        input_artifact = Artifact(
            type=ArtifactType.VIDEO,
            path=str(input_path),
            metadata={}
        )
        
        # Add mute windows file to metadata if provided
        if mute_windows:
            mute_windows_path = Path(mute_windows)
            if not mute_windows_path.exists():
                rprint(f"[red]Error: Mute windows file '{mute_windows}' not found[/red]")
                raise typer.Exit(1)
            input_artifact.metadata["mute_windows_file"] = str(mute_windows_path)
        
        # Validate flag combinations early
        if force and skip_existing:
            rprint(f"[red]Error: --force and --skip-existing cannot be used together[/red]")
            raise typer.Exit(1)
        
        if jobs <= 0:
            rprint(f"[red]Error: --jobs must be a positive integer, got {jobs}[/red]")
            raise typer.Exit(1)
        
        # Create operation flags using smart defaults and config values
        flags = OperationFlags(
            dry_run=dry_run,
            verbose=verbose,
            strategy="default",
            force=force,
            skip_existing=skip_existing,
            parallel=parallel,
            max_jobs=jobs,
            continue_on_qc_fail=continue_on_qc_fail,
            continue_on_audio_qc_fail=continue_on_audio_qc_fail,
            audio_qc_threshold_db=audio_qc_threshold_db,
            audio_qc_control_window=audio_qc_control_window,
            profanity_list_file=profanity_list_file,
            fuzzy_threshold=fuzzy_threshold,
            subtitle_mode=subtitle_mode,
            create_subtitle_sidecar=create_subtitle_sidecar,
            sidecar_tag=sidecar_tag,
            strict_audio_parity=strict_audio_parity,
            persist_intermediate=persist_intermediate,
            final_dest=final_dest,
            output_mode=effective_output_mode,
            backup=effective_backup,
            dest_policy=effective_dest_policy or "subfolder_tag",
            dest_policy_tag=effective_dest_policy_tag or "[Censorr]",
            dest_separate_root=effective_dest_separate_root or "/data/media/TV/Censorr",
            conflict_policy="reuse_if_identical",
            # Audio encoding smart defaults - always preserve original (per user requirement)
            audio_transcode_to_original=audio_transcode_to_original,
            audio_target_codec=audio_target_codec,
            audio_bitrate=audio_bitrate,  # None = preserve original
            audio_channels=audio_channels,  # None = preserve original
            prune_non_clean_tracks=prune_non_clean_tracks
        )
        
        # Plan operations
        if verbose:
            rprint("[blue]Planning operations...[/blue]")
            
            # Show execution mode
            if flags.parallel:
                rprint(f"[blue]Execution mode: Parallel ({flags.max_jobs} jobs)[/blue]")
            else:
                rprint("[blue]Execution mode: Sequential[/blue]")
            
            if flags.force:
                rprint("[yellow]Force mode: Will overwrite existing files[/yellow]")
            elif flags.skip_existing:
                rprint("[yellow]Skip mode: Will skip existing files[/yellow]")
        
        # Create registry and planner
        registry = create_operation_registry()
        planner = Planner(registry)
        
        # Determine target artifact types from operations
        target_types = determine_target_types(operation_list, registry)
        
        plan = planner.plan(
            [input_artifact],
            target_types,
            selectors=selectors,
            requested_operations=operation_list
        )
        
        if verbose or dry_run:
            rprint("[blue]Execution plan:[/blue]")
            for i, operation in enumerate(plan.operations, 1):
                rprint(f"  {i}. {operation.name}")
                if verbose:
                    rprint(f"     - Consumes: {', '.join(t.value for t in operation.consumes)}")
                    rprint(f"     - Produces: {', '.join(t.value for t in operation.produces)}")
        
        if dry_run:
            rprint("[yellow]Dry run mode - no files will be modified[/yellow]")
            return
        
        # Execute operations
        if verbose:
            rprint("[blue]Executing operations...[/blue]")
        
        executor = Executor()
        results = executor.execute(plan, output_path, artifacts=[input_artifact], flags=flags)
        
        # Post-processing: cleanup and final destination
        from src.utils.cleanup_manager import CleanupManager
        from src.utils.final_destination import FinalDestinationManager
        
        # Handle cleanup and final destination
        if results and any(result.success for result in results):
            # Collect final output files
            final_output_files = []
            for result in results:
                if result.success and hasattr(result, 'output_files'):
                    final_output_files.extend(result.output_files)
            
            # Find remuxed video files in output directory (fallback)
            if not final_output_files:
                final_output_files = list(output_path.glob("remuxed_*.mkv")) + list(output_path.glob("remuxed_*.mp4"))
                final_output_files = [str(f) for f in final_output_files]
            
            # Cleanup intermediate files
            cleanup_manager = CleanupManager()
            # Register common intermediate patterns
            for pattern in ["extract_audio/*/*", "mute_audio/*/*", "extract_subtitles/*/*", "merge_subtitles/*/*", "mask_subtitles/*/*"]:
                for intermediate_file in output_path.glob(pattern):
                    cleanup_manager.register_intermediate(str(intermediate_file))
            
            # Register final outputs as preserved
            for final_file in final_output_files:
                cleanup_manager.register_preserved(final_file)
            
            cleanup_result = cleanup_manager.cleanup_intermediates(flags.persist_intermediate)
            if verbose and cleanup_result["status"] != "skipped":
                rprint(f"[blue]Cleanup: {cleanup_result['cleaned_count']} intermediate files removed[/blue]")
            elif verbose:
                rprint(f"[blue]Cleanup: Skipped ({cleanup_result['reason']})[/blue]")
            
            # Move to final destination
            if flags.final_dest and final_output_files:
                dest_manager = FinalDestinationManager()
                move_result = dest_manager.move_to_final_destination(final_output_files, flags.final_dest)
                if verbose:
                    if move_result["status"] == "completed":
                        rprint(f"[blue]Final destination: {move_result['moved_count']} files moved to {flags.final_dest}[/blue]")
                    else:
                        rprint(f"[yellow]Final destination: {move_result.get('message', 'Failed')}[/yellow]")

        # Report results
        if results:
            rprint(f"[green]✓ Processing complete! Generated {len(results)} operation results[/green]")
            for result in results:
                if result.success:
                    rprint(f"  - ✓ {result.operation}: Success")
                else:
                    rprint(f"  - ✗ {result.operation}: Failed")
        else:
            rprint("[yellow]No output files generated[/yellow]")
            
    except Exception as e:
        if verbose:
            rprint(f"[red]Error details: {e}[/red]")
            import traceback
            traceback.print_exc()
        else:
            rprint(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command("list-operations")
def list_operations():
    """
    List all available operations and their descriptions.
    """
    rprint("[bold blue]Available Operations:[/bold blue]")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Operation", style="cyan", min_width=20)
    table.add_column("Description", style="white")
    
    for operation in AVAILABLE_OPERATIONS:
        description = OPERATION_DESCRIPTIONS.get(operation, "No description available")
        table.add_row(operation, description)
    
    console.print(table)


@app.command()
def explain():
    """
    Explain the censorr pipeline and available operations.
    """
    rprint("[bold blue]Censorr Pipeline Overview[/bold blue]")
    rprint("")
    rprint("Censorr processes media files through a series of operations:")
    rprint("")
    
    rprint("[bold green]1. Extraction Phase[/bold green]")
    rprint("   • subtitle_extract: Extract subtitle tracks from video")
    rprint("   • audio_extract: Extract audio tracks from video")
    rprint("")
    
    rprint("[bold yellow]2. Processing Phase[/bold yellow]")
    rprint("   • subtitle_merge: Combine multiple subtitle files")
    rprint("   • subtitle_mask: Apply profanity filtering to subtitles")
    rprint("   • audio_mute: Apply mute windows to audio tracks")
    rprint("")
    
    rprint("[bold cyan]3. Quality Control Phase[/bold cyan]")
    rprint("   • audio_qc: Verify audio muting effectiveness through energy analysis")
    rprint("   • subtitle_qc: Verify subtitle masking effectiveness and detect residual profanity")
    rprint("")
    
    rprint("[bold magenta]4. Export Phase[/bold magenta]")
    rprint("   • subtitle_export: Create external subtitle/metadata files")
    rprint("   • video_remux: Combine all processed tracks into final video")
    rprint("")
    
    rprint("[bold blue]Example Usage:[/bold blue]")
    rprint("  # Basic processing")
    rprint("  censorr process movie.mp4 --output ./censored/")
    rprint("")
    rprint("  # Dry run to see what would happen")
    rprint("  censorr process movie.mp4 --dry-run --verbose")
    rprint("")
    rprint("  # Process only specific operations")
    rprint("  censorr process movie.mp4 --operations extract_subtitles,mask_subtitles")
    rprint("")
    rprint("  # Use external mute windows")
    rprint("  censorr process movie.mp4 --mute-windows mute_times.json")


if __name__ == "__main__":
    app()


@app.command()
def webhook():
    """
    Handle a webhook payload from stdin (JSON) and dispatch to processing.

    Exit codes:
      0 -> accepted (at least one job queued/processed)
      2 -> ignored (missing/unknown preset, or no actionable media paths)
      3 -> failed (malformed payload or security validation failed)
    """
    try:
        raw = sys.stdin.read()
        if not raw:
            raise ValueError("empty payload")
        payload = json.loads(raw)
    except Exception:
        raise typer.Exit(code=3)

    # Validate basic shape
    if not isinstance(payload, dict):
        raise typer.Exit(code=3)

    tags = payload.get("tags")
    if not isinstance(tags, dict):
        # No tags object: nothing to do per server contract
        raise typer.Exit(code=2)

    preset = tags.get("censorr_preset")
    try:
        app_config = Config.load_with_fallback(None)
    except Exception:
        app_config = Config()

    if not preset:
        # Missing preset is ignored
        raise typer.Exit(code=2)

    # Unknown preset: ignore (contract 200 ignored)
    if preset not in app_config.presets:
        raise typer.Exit(code=2)

    # Media paths
    media_paths = payload.get("mediaPaths")
    if not isinstance(media_paths, list) or not media_paths:
        raise typer.Exit(code=2)

    # Process each existing path; consider success if at least one processed
    any_success = False
    for path in media_paths:
        try:
            if not isinstance(path, str):
                continue
            p = Path(path)
            if not p.exists():
                # Fail gracefully: log and continue
                if app_config and app_config.verbose:
                    rprint(f"[yellow]Path does not exist, skipping: {path}[/yellow]")
                continue
            # Call the process function programmatically
            try:
                process(  # type: ignore[misc]
                    input_file=str(p),
                    config=None,
                    output="./output",
                    operations=None,
                    language=None,
                    mute_windows=None,
                    dry_run=False,
                    verbose=False,
                    force=False,
                    profanity_list_file=None,
                    create_subtitle_sidecar=False,
                    preset=preset,
                )
                any_success = True
            except typer.Exit as te:
                # Non-zero exits from process indicate a failure for this path
                if te.exit_code == 0:
                    any_success = True
                else:
                    # Continue to try other paths
                    continue
        except Exception:
            # Continue with other paths
            continue

    if any_success:
        raise typer.Exit(code=0)
    else:
        # Nothing actionable
        raise typer.Exit(code=2)