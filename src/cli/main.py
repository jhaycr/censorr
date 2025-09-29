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
from src.models.config import Config
from src.planner.planner import Planner
from src.planner.registry import OperationRegistry
from src.planner.executor import Executor

# Import all available operations
from src.ops.extract_subtitles import ExtractSubtitlesOperation
from src.ops.merge_subtitles import MergeSubtitlesOperation
from src.ops.mask_subtitles import MaskSubtitlesOperation
from src.ops.export_sidecar import ExportSidecarOperation
from src.ops.extract_audio import ExtractAudioOperation
from src.ops.mute_audio import MuteAudioOperation
from src.ops.audio_quality_check import AudioQualityCheckOperation
from src.ops.remux import RemuxOperation

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
    registry.register(ExportSidecarOperation())
    registry.register(ExtractAudioOperation())
    registry.register(MuteAudioOperation())
    registry.register(AudioQualityCheckOperation())
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
    "extract_subtitles",
    "merge_subtitles", 
    "mask_subtitles",
    "export_sidecar",
    "extract_audio",
    "mute_audio",
    "audio_quality_check",
    "remux"
]

OPERATION_DESCRIPTIONS = {
    "extract_subtitles": "Extract subtitle tracks from video files",
    "merge_subtitles": "Combine multiple subtitle files into one",
    "mask_subtitles": "Apply profanity filtering to subtitle content",
    "export_sidecar": "Create external subtitle/metadata files",
    "extract_audio": "Extract audio tracks from video files",
    "mute_audio": "Apply mute windows to audio tracks",
    "audio_quality_check": "Verify audio muting effectiveness through energy analysis",
    "remux": "Combine processed tracks into final video"
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
    track_index: Optional[int] = typer.Option(
        None, "--track-index", "-t",
        help="Filter by track index (not yet supported)"
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
    skip_existing: bool = typer.Option(
        False, "--skip-existing", "-s",
        help="Skip processing if output already exists"
    ),
    parallel: bool = typer.Option(
        False, "--parallel", "-p",
        help="Enable parallel execution of operations"
    ),
    jobs: int = typer.Option(
        1, "--jobs", "-j",
        help="Number of parallel jobs (automatically enables parallel mode)"
    ),
    continue_on_qc_fail: bool = typer.Option(
        False, "--continue-on-qc-fail",
        help="Continue pipeline execution despite QC failures (residual profane matches)"
    ),
    continue_on_audio_qc_fail: bool = typer.Option(
        False, "--continue-on-audio-qc-fail",
        help="Continue pipeline execution despite audio QC failures (insufficient muting)"
    ),
    subtitle_title_include: Optional[str] = typer.Option(
        None, "--subtitle-title-include",
        help="Include subtitle tracks with titles containing these substrings (comma-separated)"
    ),
    subtitle_title_exclude: Optional[str] = typer.Option(
        None, "--subtitle-title-exclude", 
        help="Exclude subtitle tracks with titles containing these substrings (comma-separated)"
    ),
    subtitle_title_regex: Optional[str] = typer.Option(
        None, "--subtitle-title-regex",
        help="Include subtitle tracks with titles matching these regex patterns (comma-separated)"
    ),
    profanity_list_file: Optional[str] = typer.Option(
        None, "--profanity-list-file",
        help="Path to JSON file with an array of {word: string, ...} objects for profanity masking"
    ),
    fuzzy_threshold: Optional[float] = typer.Option(
        None, "--fuzzy-threshold",
        help="Similarity threshold (0-100) for fuzzy profanity matching"
    ),
    subtitle_mode: str = typer.Option(
        "masked_only", "--subtitle-mode",
        help="How to handle subtitles in remux: 'all', 'masked_only', or 'none'"
    ),
    create_subtitle_sidecar: bool = typer.Option(
        False, "--create-subtitle-sidecar",
        help="Create sidecar subtitle files alongside remuxed video"
    ),
    sidecar_tag: str = typer.Option(
        "censorr", "--sidecar-tag",
        help="Tag to use in sidecar subtitle filenames (censorr or clean)"
    ),
    strict_audio_parity: bool = typer.Option(
        False, "--strict-audio-parity",
        help="Fail on audio codec/format mismatches in remux; default warn only"
    ),
    persist_intermediate: bool = typer.Option(
        False, "--persist-intermediate",
        help="Keep intermediate artifacts after successful completion"
    ),
    final_dest: Optional[str] = typer.Option(
        None, "--final-dest",
        help="Final destination directory to move completed outputs"
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
        
        # Merge config with CLI arguments (CLI args take precedence)
        # For boolean flags, we need to detect if they were explicitly set or using default
        merged_args = app_config.merge_with_args(
            output=output if output != "./output" else None,  # Only override if not default
            dry_run=dry_run if dry_run else None,  # Only override if True
            verbose=verbose if verbose else None,  # Only override if True
            force=force if force else None,  # Only override if True
            skip_existing=skip_existing if skip_existing else None,  # Only override if True
            parallel=parallel if parallel else None,  # Only override if True
            jobs=jobs if jobs != 1 else None,  # Only override if not default
            continue_on_qc_fail=continue_on_qc_fail if continue_on_qc_fail else None,
            continue_on_audio_qc_fail=continue_on_audio_qc_fail if continue_on_audio_qc_fail else None,
            subtitle_title_include=subtitle_title_include,
            subtitle_title_exclude=subtitle_title_exclude,
            subtitle_title_regex=subtitle_title_regex,
            language=language,
            fuzzy_threshold=fuzzy_threshold,
            subtitle_mode=subtitle_mode if subtitle_mode != "masked_only" else None,
            sidecar_tag=sidecar_tag if sidecar_tag != "censorr" else None,
            strict_audio_parity=strict_audio_parity if strict_audio_parity else None,
            profanity_list_file=profanity_list_file
        )
        
        # Use merged values for the rest of the function
        output = merged_args['output']
        dry_run = merged_args['dry_run']
        verbose = merged_args['verbose']
        force = merged_args['force']
        skip_existing = merged_args['skip_existing']
        parallel = merged_args['parallel']
        jobs = merged_args['jobs']
        continue_on_qc_fail = merged_args['continue_on_qc_fail']
        continue_on_audio_qc_fail = merged_args['continue_on_audio_qc_fail']
        subtitle_title_include = ','.join(merged_args['subtitle_title_include']) if merged_args['subtitle_title_include'] else None
        subtitle_title_exclude = ','.join(merged_args['subtitle_title_exclude']) if merged_args['subtitle_title_exclude'] else None
        subtitle_title_regex = ','.join(merged_args['subtitle_title_regex']) if merged_args['subtitle_title_regex'] else None
        language = merged_args['language']
        fuzzy_threshold = merged_args['fuzzy_threshold']
        subtitle_mode = merged_args['subtitle_mode']
        sidecar_tag = merged_args['sidecar_tag']
        strict_audio_parity = merged_args['strict_audio_parity']
        profanity_list_file = merged_args['profanity_list_file']
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
        
        # Create selectors
        selectors = []
        
        # Parse title filter lists
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
        
        # Create operation flags using merged values
        flags = OperationFlags(
            dry_run=merged_args['dry_run'],
            verbose=merged_args['verbose'],
            strategy="default",
            force=merged_args['force'],
            skip_existing=merged_args['skip_existing'],
            parallel=merged_args['parallel'],
            max_jobs=merged_args['jobs'],
            continue_on_qc_fail=merged_args['continue_on_qc_fail'],
            continue_on_audio_qc_fail=merged_args['continue_on_audio_qc_fail'],
            profanity_list_file=merged_args['profanity_list_file'],
            fuzzy_threshold=merged_args['fuzzy_threshold'],
            subtitle_mode=merged_args['subtitle_mode'],
            create_subtitle_sidecar=create_subtitle_sidecar,
            sidecar_tag=merged_args['sidecar_tag'],
            strict_audio_parity=merged_args['strict_audio_parity'],
            persist_intermediate=persist_intermediate,
            final_dest=final_dest
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
    rprint("   • extract_subtitles: Extract subtitle tracks from video")
    rprint("   • extract_audio: Extract audio tracks from video")
    rprint("")
    
    rprint("[bold yellow]2. Processing Phase[/bold yellow]")
    rprint("   • merge_subtitles: Combine multiple subtitle files")
    rprint("   • mask_subtitles: Apply profanity filtering to subtitles")
    rprint("   • mute_audio: Apply mute windows to audio tracks")
    rprint("")
    
    rprint("[bold cyan]3. Quality Control Phase[/bold cyan]")
    rprint("   • audio_quality_check: Verify audio muting effectiveness through energy analysis")
    rprint("")
    
    rprint("[bold magenta]4. Export Phase[/bold magenta]")
    rprint("   • export_sidecar: Create external subtitle/metadata files")
    rprint("   • remux: Combine all processed tracks into final video")
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