"""Structured logging system for the censorr package."""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.models.artifacts import Artifact
from src.models.common import AuditLogEntry, LogLevel


class OperationLogEntry(BaseModel):
    """Structured log entry for a single operation execution."""
    
    operation: str = Field(..., description="Operation name")
    start_time: datetime = Field(..., description="Operation start time")
    end_time: Optional[datetime] = Field(None, description="Operation end time")
    duration_ms: Optional[float] = Field(None, description="Duration in milliseconds")
    success: bool = Field(..., description="Whether operation succeeded")
    inputs: List[Dict[str, Any]] = Field(default_factory=list, description="Input artifacts info")
    outputs: List[Dict[str, Any]] = Field(default_factory=list, description="Output artifacts info")
    workdir: str = Field(..., description="Working directory used")
    flags: Dict[str, Any] = Field(default_factory=dict, description="Operation flags")
    error: Optional[str] = Field(None, description="Error message if failed")
    external_commands: List[Dict[str, Any]] = Field(default_factory=list, description="External commands executed")
    logs: List[str] = Field(default_factory=list, description="Operation log messages")
    
    def mark_finished(self, success: bool, error: Optional[str] = None):
        """Mark the operation as finished."""
        self.end_time = datetime.now()
        if self.start_time:
            delta = self.end_time - self.start_time
            self.duration_ms = delta.total_seconds() * 1000
        self.success = success
        if error:
            self.error = error


class ExecutionLogger:
    """Manages structured logging for operation execution."""
    
    def __init__(self, workdir: Path, session_id: Optional[str] = None):
        """Initialize the execution logger.
        
        Args:
            workdir: Working directory for logs
            session_id: Optional session identifier
        """
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.execution_log_path = self.workdir / f"execution_{self.session_id}.json"
        self.audit_log_path = self.workdir / f"audit_{self.session_id}.json"
        
        # Track current operation logs
        self.operation_logs: List[OperationLogEntry] = []
        self.audit_entries: List[AuditLogEntry] = []
        
        # Set up Python logger for this session
        self.logger = logging.getLogger(f"censorr.{self.session_id}")
        if not self.logger.handlers:
            handler = logging.FileHandler(self.workdir / f"session_{self.session_id}.log")
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def start_operation(
        self, 
        operation_name: str, 
        inputs: List[Artifact], 
        workdir: Path,
        flags: Dict[str, Any]
    ) -> OperationLogEntry:
        """Start logging for an operation.
        
        Args:
            operation_name: Name of the operation
            inputs: Input artifacts
            workdir: Operation working directory
            flags: Operation flags
            
        Returns:
            Operation log entry
        """
        # Convert inputs to serializable format
        input_info = []
        for artifact in inputs:
            input_info.append({
                "type": str(artifact.type),
                "path": artifact.path,
                "metadata": artifact.metadata,
                "exists": Path(artifact.path).exists(),
                "size_bytes": Path(artifact.path).stat().st_size if Path(artifact.path).exists() else 0
            })
        
        log_entry = OperationLogEntry(
            operation=operation_name,
            start_time=datetime.now(),
            success=False,  # Will be updated on completion
            inputs=input_info,
            workdir=str(workdir),
            flags=flags
        )
        
        self.operation_logs.append(log_entry)
        
        # Add audit entry
        self.add_audit_entry(
            operation_name, 
            LogLevel.INFO, 
            f"Started operation {operation_name}",
            {
                "inputs": len(inputs),
                "workdir": str(workdir),
                "flags": flags
            }
        )
        
        self.logger.info(f"Started operation: {operation_name}")
        return log_entry
    
    def finish_operation(
        self, 
        log_entry: OperationLogEntry, 
        success: bool, 
        outputs: List[Artifact] = None,
        error: Optional[str] = None
    ):
        """Finish logging for an operation.
        
        Args:
            log_entry: Operation log entry to finish
            success: Whether operation succeeded
            outputs: Output artifacts
            error: Error message if failed
        """
        if outputs is None:
            outputs = []
        
        # Convert outputs to serializable format
        output_info = []
        for artifact in outputs:
            output_info.append({
                "type": str(artifact.type),
                "path": artifact.path,
                "metadata": artifact.metadata,
                "exists": Path(artifact.path).exists(),
                "size_bytes": Path(artifact.path).stat().st_size if Path(artifact.path).exists() else 0
            })
        
        log_entry.outputs = output_info
        log_entry.mark_finished(success, error)
        
        # Add audit entry
        level = LogLevel.INFO if success else LogLevel.ERROR
        message = f"Completed operation {log_entry.operation}" if success else f"Failed operation {log_entry.operation}: {error}"
        
        self.add_audit_entry(
            log_entry.operation, 
            level, 
            message,
            {
                "success": success,
                "duration_ms": log_entry.duration_ms,
                "outputs": len(outputs),
                "error": error
            }
        )
        
        self.logger.info(f"Finished operation: {log_entry.operation} (success={success})")
        
        # Save logs after each operation
        self.save_logs()
    
    def log_external_command(
        self, 
        log_entry: OperationLogEntry, 
        command: List[str], 
        exit_code: int,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        duration_ms: Optional[float] = None
    ):
        """Log an external command execution.
        
        Args:
            log_entry: Operation log entry
            command: Command that was executed
            exit_code: Command exit code
            stdout: Command stdout
            stderr: Command stderr
            duration_ms: Command duration in milliseconds
        """
        command_info = {
            "command": command,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "timestamp": datetime.now().isoformat(),
            "stdout_path": None,
            "stderr_path": None
        }
        
        # Save stdout/stderr to files if provided
        if stdout or stderr:
            cmd_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            
            if stdout:
                stdout_path = self.workdir / f"{log_entry.operation}_{cmd_timestamp}_stdout.txt"
                stdout_path.write_text(stdout)
                command_info["stdout_path"] = str(stdout_path)
            
            if stderr:
                stderr_path = self.workdir / f"{log_entry.operation}_{cmd_timestamp}_stderr.txt"
                stderr_path.write_text(stderr)
                command_info["stderr_path"] = str(stderr_path)
        
        log_entry.external_commands.append(command_info)
        
        # Add audit entry for external command
        level = LogLevel.INFO if exit_code == 0 else LogLevel.ERROR
        message = f"External command: {' '.join(command[:3])}..." if len(command) > 3 else f"External command: {' '.join(command)}"
        
        self.add_audit_entry(
            log_entry.operation,
            level,
            message,
            {
                "command": command,
                "exit_code": exit_code,
                "duration_ms": duration_ms
            }
        )
    
    def add_operation_log(self, log_entry: OperationLogEntry, message: str):
        """Add a log message to an operation.
        
        Args:
            log_entry: Operation log entry
            message: Log message
        """
        log_entry.logs.append(f"{datetime.now().isoformat()}: {message}")
    
    def add_audit_entry(
        self, 
        operation: str, 
        level: LogLevel, 
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Add an audit log entry.
        
        Args:
            operation: Operation name
            level: Log level
            message: Log message
            details: Additional details
        """
        entry = AuditLogEntry(
            op=operation,
            level=level,
            message=message,
            details=details or {}
        )
        self.audit_entries.append(entry)
    
    def save_logs(self):
        """Save all logs to files."""
        # Save execution log
        execution_data = {
            "session_id": self.session_id,
            "start_time": self.operation_logs[0].start_time.isoformat() if self.operation_logs else None,
            "end_time": self.operation_logs[-1].end_time.isoformat() if self.operation_logs and self.operation_logs[-1].end_time else None,
            "operations": [entry.model_dump() for entry in self.operation_logs]
        }
        
        with self.execution_log_path.open('w') as f:
            json.dump(execution_data, f, indent=2, default=str)
        
        # Save audit log
        audit_data = {
            "session_id": self.session_id,
            "entries": [entry.model_dump() for entry in self.audit_entries]
        }
        
        with self.audit_log_path.open('w') as f:
            json.dump(audit_data, f, indent=2, default=str)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the execution.
        
        Returns:
            Execution summary
        """
        total_operations = len(self.operation_logs)
        successful_operations = sum(1 for log in self.operation_logs if log.success)
        failed_operations = total_operations - successful_operations
        
        total_duration = sum(
            log.duration_ms or 0 for log in self.operation_logs if log.duration_ms
        )
        
        return {
            "session_id": self.session_id,
            "total_operations": total_operations,
            "successful_operations": successful_operations,
            "failed_operations": failed_operations,
            "total_duration_ms": total_duration,
            "execution_log": str(self.execution_log_path),
            "audit_log": str(self.audit_log_path)
        }