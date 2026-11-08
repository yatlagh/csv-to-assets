"""csv-to-assets: CSV-driven batch generation of PNG thumbnails and PDFs."""

from .template import Template, load_template
from .pipeline import generate, GenerateOptions, Summary

__version__ = "0.1.0"
__all__ = ["Template", "load_template", "generate", "GenerateOptions", "Summary", "__version__"]
