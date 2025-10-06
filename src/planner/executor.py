"""Executor for running planned operations."""
from typing import List, Optional
from pathlib import Path
from dataclasses import dataclass
import logging
from ..models.artifacts import Artifact, ArtifactType
from ..models.operations import OperationFlags, OperationResult
from ..caching import CacheManager
from ..logging import ExecutionLogger
from .planner import ExecutionPlan


@dataclass
class ExecutionContext:
    """Context for operation execution."""
    
    workdir: Path
    flags: OperationFlags
    artifacts: List[Artifact] = None
    cache_manager: Optional[CacheManager] = None
    execution_logger: Optional[ExecutionLogger] = None
    
    def __post_init__(self):
        if self.artifacts is None:
            self.artifacts = []
        if self.cache_manager is None:
            self.cache_manager = CacheManager(self.workdir)
        if self.execution_logger is None:
            self.execution_logger = ExecutionLogger(self.workdir)


class Executor:
    """Executes planned operations."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def execute(
        self, 
        plan: ExecutionPlan, 
        workdir: Path,
        artifacts: Optional[List[Artifact]] = None,
        flags: Optional[OperationFlags] = None
    ) -> List[OperationResult]:
        """Execute the planned operations.
        
        Args:
            plan: Execution plan to run
            workdir: Working directory for outputs
            artifacts: Initial artifacts available
            flags: Execution flags
            
        Returns:
            List of operation results
        """
        if artifacts is None:
            artifacts = []
        
        if flags is None:
            flags = OperationFlags()
        
        # Include selectors from plan in flags
        if plan.selectors and not flags.selectors:
            flags.selectors = plan.selectors
        
        context = ExecutionContext(
            workdir=workdir,
            flags=flags,
            artifacts=artifacts.copy()
        )
        
        results = []
        
        for operation in plan.operations:
            result = self._execute_operation(operation, context)
            results.append(result)
            
            # If operation succeeded, add its outputs to available artifacts
            if result.success:
                # In a real implementation, we'd parse the outputs
                # For now, just log the success
                if flags.verbose:
                    self.logger.info(f"Operation {operation.name} completed successfully")
        
        # Generate final execution summary
        if context.execution_logger:
            summary = context.execution_logger.get_summary()
            if flags.verbose:
                self.logger.info(f"Execution summary: {summary}")
        
        return results
    
    def _execute_operation(
        self, 
        operation, 
        context: ExecutionContext
    ) -> OperationResult:
        """Execute a single operation.
        
        Args:
            operation: Operation to execute
            context: Execution context
            
        Returns:
            Operation result
        """
        # Find input artifacts that match operation requirements
        input_artifacts = self._find_inputs(operation, context.artifacts)
        
        # Start operation logging
        operation_flags_dict = {
            "verbose": context.flags.verbose,
            "dry_run": context.flags.dry_run,
            "force": context.flags.force,
            "skip_existing": context.flags.skip_existing
        }
        
        log_entry = context.execution_logger.start_operation(
            operation.name, input_artifacts, context.workdir, operation_flags_dict
        )
        
        try:
            if context.flags.verbose:
                self.logger.info(f"Executing operation: {operation.name}")
                context.execution_logger.add_operation_log(
                    log_entry, f"Starting execution with {len(input_artifacts)} inputs"
                )
            
            if context.flags.dry_run:
                self.logger.info(f"DRY RUN: Would execute {operation.name}")
                context.execution_logger.add_operation_log(log_entry, "DRY RUN mode - no actual execution")
                context.execution_logger.finish_operation(log_entry, True, [])
                
                return OperationResult(
                    operation=operation.name,
                    inputs=[],
                    outputs=[],
                    success=True,
                    logs=[f"DRY RUN: {operation.name}"]
                )
            
            # Check if operation is cached (unless skip_existing flag is set)
            operation_params = {
                "verbose": context.flags.verbose,
                "dry_run": context.flags.dry_run,
                "force": context.flags.force,
                "skip_existing": context.flags.skip_existing
            }
            # Incorporate selectors into cache key so language/title filters affect caching
            if context.flags.selectors:
                try:
                    selectors_fp = []
                    for s in context.flags.selectors:
                        selectors_fp.append({
                            "type": getattr(s.type, "value", str(s.type)),
                            "language": getattr(s, "language", None),
                            "role": getattr(s, "role", None),
                            "codec": getattr(s, "codec", None),
                            "forced": getattr(s, "forced", None),
                            "title_include": getattr(s, "title_include", None),
                            "title_exclude": getattr(s, "title_exclude", None),
                            "title_regex": getattr(s, "title_regex", None),
                            "first_only": getattr(s, "first_only", None),
                            "priority": getattr(s, "priority", None),
                        })
                    # Sort for stability
                    operation_params["selectors"] = sorted(
                        selectors_fp, key=lambda x: (
                            x.get("type"), x.get("language"), x.get("forced"),
                            tuple(x.get("title_include") or []), tuple(x.get("title_exclude") or []), tuple(x.get("title_regex") or [])
                        )
                    )
                except Exception:
                    # If anything goes wrong, fall back to basic params (no selector fingerprint)
                    pass
            
            is_cached, operation_dir = context.cache_manager.is_cached(
                operation.name, input_artifacts, operation_params, context.flags
            )
            
            # If operation_dir is None (force flag case), get it manually
            if operation_dir is None:
                cache_key = context.cache_manager.create_cache_key(
                    operation.name, input_artifacts, operation_params
                )
                operation_dir = context.cache_manager.get_operation_dir(operation.name, cache_key)
            
            if is_cached and not context.flags.skip_existing:
                if context.flags.verbose:
                    # Log to file logger and also surface to console so users understand missing per-op logs
                    self.logger.info(f"Operation {operation.name} cached, skipping execution")
                    print(f"[executor] Using cached result for '{operation.name}' at {operation_dir}. Pass --force to re-run.")
                    context.execution_logger.add_operation_log(
                        log_entry, f"Found cached result in {operation_dir}"
                    )
                
                # Load outputs from manifest
                manifest = context.cache_manager.load_manifest(operation_dir)
                if manifest:
                    # Reconstruct output artifacts from manifest
                    output_artifacts = []
                    for output_entry in manifest.outputs:
                        output_path = Path(output_entry["path"])
                        if output_path.exists():
                            # Determine artifact type from file extension (simple heuristic)
                            if output_path.suffix.lower() in ['.srt', '.vtt', '.ass']:
                                artifact_type = ArtifactType.SUBTITLE
                                # Try to infer language from filename pattern: base.lang.index.ext
                                name_parts = output_path.name.split('.')
                                inferred_lang = None
                                if len(name_parts) >= 3:
                                    # e.g., Movie Title.eng.1.srt -> 'eng'
                                    inferred_lang = name_parts[-3]
                                    # normalize common 3-letter codes to 2-letter where appropriate
                                    if inferred_lang == 'eng':
                                        inferred_lang = 'en'
                                metadata = {"language": inferred_lang or "und"}
                            elif output_path.suffix.lower() in ['.mp3', '.wav', '.flac', '.m4a']:
                                artifact_type = ArtifactType.AUDIO
                                metadata = {"channels": "stereo"}  # Default metadata
                            elif output_path.suffix.lower() in ['.mp4', '.mkv', '.avi']:
                                artifact_type = ArtifactType.VIDEO
                                metadata = {"codec": "unknown"}  # Default metadata
                            else:
                                artifact_type = ArtifactType.SIDECAR
                                metadata = {}
                            
                            output_artifact = Artifact(
                                type=artifact_type,
                                path=str(output_path),
                                metadata=metadata
                            )
                            output_artifacts.append(output_artifact)
                    
                    # Update context with cached artifacts
                    context.artifacts.extend(output_artifacts)
                    
                    # Finish logging
                    context.execution_logger.finish_operation(log_entry, True, output_artifacts)
                    
                    return OperationResult(
                        operation=operation.name,
                        inputs=[artifact.path for artifact in input_artifacts],
                        outputs=[artifact.path for artifact in output_artifacts],
                        success=True,
                        logs=[f"Loaded from cache: {operation_dir}"]
                    )
            
            # Execute the operation
            context.execution_logger.add_operation_log(log_entry, "Executing operation")
            outputs = operation.run(input_artifacts, operation_dir, context.flags)
            
            context.execution_logger.add_operation_log(
                log_entry, f"Operation completed with {len(outputs)} outputs"
            )
            
            # Save manifest for caching
            context.cache_manager.save_manifest(
                operation_dir, operation.name, input_artifacts, outputs, operation_params
            )
            
            # Update context with new artifacts
            context.artifacts.extend(outputs)
            
            # Finish logging
            context.execution_logger.finish_operation(log_entry, True, outputs)
            
            return OperationResult(
                operation=operation.name,
                inputs=[artifact.path for artifact in input_artifacts],
                outputs=[artifact.path for artifact in outputs],
                success=True,
                logs=[f"Executed and cached in: {operation_dir}"]
            )
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Operation {operation.name} failed: {error_msg}")
            context.execution_logger.add_operation_log(log_entry, f"Error: {error_msg}")
            context.execution_logger.finish_operation(log_entry, False, error=error_msg)
            
            return OperationResult(
                operation=operation.name,
                inputs=[],
                outputs=[],
                success=False,
                error=error_msg
            )
    
    def _find_inputs(self, operation, available_artifacts: List[Artifact]) -> List[Artifact]:
        """Find input artifacts for an operation.
        
        Args:
            operation: Operation needing inputs
            available_artifacts: Available artifacts
            
        Returns:
            List of matching input artifacts
        """
        inputs = []
        
        for required_type in operation.consumes:
            matching_artifacts = [
                artifact for artifact in available_artifacts
                if artifact.type == required_type
            ]

            if not matching_artifacts:
                continue

            # If the operation consumes subtitles, pass all subtitle artifacts
            if required_type == ArtifactType.SUBTITLE:
                inputs.extend(matching_artifacts)
                continue

            # Prefer the most recently produced artifact for non-subtitle types
            chosen = None

            # Special handling for audio_quality_check: prefer AUDIO with mute window metadata
            if operation.name == "audio_quality_check" and required_type == ArtifactType.AUDIO:
                for candidate in reversed(matching_artifacts):
                    meta = candidate.metadata or {}
                    if (
                        meta.get("mute_windows_file")
                        or (isinstance(meta.get("mute_windows_applied"), int) and meta.get("mute_windows_applied", 0) > 0)
                        or (isinstance(meta.get("mute_windows"), list) and len(meta.get("mute_windows")) > 0)
                    ):
                        chosen = candidate
                        break

            # Fallback: choose the first artifact of the required type (preserve historical behavior)
            if chosen is None:
                chosen = matching_artifacts[0]

            inputs.append(chosen)
        
        return inputs