# Synthetic fixtures

The JSONL files in this directory are synthetic test data. Paths, session
identifiers, prompts, model names, and token counts are deliberately fake and
must not be replaced with real user transcripts.

The fixtures include malformed lines and unknown model names so parsers can be
tested against partial or newer provider formats without failing the complete
session scan.
