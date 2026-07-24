# Import all activity modules → triggers self-registration
from .chooser import ChooserActivity
from .view import ViewActivity
from .share import ShareActivity

__all__ = ["ChooserActivity", "ViewActivity", "ShareActivity"]
