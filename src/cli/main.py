"""Main CLI entry point for censorr."""
import sys
from pathlib import Path
from typing import List, Optional, Tuple
import json

import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.models.selectors import Selector
from src.planner.planner import Planner
from src.planner.executor import Executor

# Create the main CLI app
app = typer.Typer(
    name="censorr",
    help="CLI tool for censoring audio and subtitles in media files",
    add_completion=False,
)

console = Console()

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
    "remux"
]

OPERATION_DESCRIPTIONS = {
    "extract_subtitles": "Extract subtitle tracks from video files",
    "merge_subtitles": "Combine multiple subtitle files into one",
    "mask_subtitles": "Apply profanity filtering to subtitle content",
    "export_sidecar": "Create external subtitle/metadata files",
    "extract_audio": "Extract audio tracks from video files",
    "mute_audio": "Apply mute windows to audio tracks",
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
    )
):
    """
    Process a media file through the censorr pipeline.
    
    Automatically extracts, processes, and remuxes audio and subtitle tracks
    to create a censored version of the input media file.
    """
    try:
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
        if language:
            # Create subtitle selector
            subtitle_selector = Selector(
                type=ArtifactType.SUBTITLE,
                language=language
            )
            selectors.append(subtitle_selector)
            
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
        
        # Create operation flags
        flags = OperationFlags(
            dry_run=dry_run,
            verbose=verbose,
            strategy="default",
            force=force,
            skip_existing=skip_existing,
            parallel=parallel,
            max_jobs=jobs
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
        
        planner = Planner()
        plan = planner.plan([input_artifact], selectors, operation_list)
        
        if verbose or dry_run:
            rprint("[blue]Execution plan:[/blue]")
            for i, (operation_name, operation_inputs) in enumerate(plan, 1):
                rprint(f"  {i}. {operation_name}")
                if verbose:
                    for artifact in operation_inputs:
                        rprint(f"     - {artifact.type.value}: {Path(artifact.path).name}")
        
        if dry_run:
            rprint("[yellow]Dry run mode - no files will be modified[/yellow]")
            return
        
        # Execute operations
        if verbose:
            rprint("[blue]Executing operations...[/blue]")
        
        executor = Executor()
        results = executor.execute(plan, output_path, flags)
        
        # Report results
        if results:
            rprint(f"[green]✓ Processing complete! Generated {len(results)} output files:[/green]")
            for result in results:
                rprint(f"  - {result.type.value}: {result.path}")
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
    
    rprint("[bold magenta]3. Export Phase[/bold magenta]")
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