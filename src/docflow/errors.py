class DocFlowError(Exception):
    """An actionable user-facing input or generation error."""



class GenerationCancelled(DocFlowError):
    """An intentional user cancellation; no completed package was published."""
