# Rough Idea: Censorr v2 Rebuild

Build a net-new version of Censorr from scratch that accomplishes the same goals as the current project:

- **Core function**: Mute profanities from audio tracks and censor (mask) them from subtitles in media files.
- **Interfaces**:
  - Direct CLI invocation.
  - A service invocable by API or webhook from Sonarr or Radarr.
- **Plex naming conventions** (emphasized): Specific naming conventions for TV episodes and movies so that the processed subtitles and audio resolve correctly in Plex. This is a first-class requirement, not an afterthought.
- **Modularization** (emphasized): Strong, deliberate modularization — pay close attention to how the user wants modules organized.
- **Sensible defaults** (emphasized): Reasonable defaults that allow execution with minimal inputs.

## Deliverable

A comprehensive, step-by-step implementation plan that can be handed off to an agent with fresh context to implement.

## Process constraints from the user

- Review the structure of the current Censorr project first.
- If anything is ambiguous, ask instead of guessing — but come with options and recommendations.

## Source

Provided directly in conversation by Josh, 2026-07-15. Existing codebase: /home/josh/Code/Censorr2 (branch feature/webhook-preset).
