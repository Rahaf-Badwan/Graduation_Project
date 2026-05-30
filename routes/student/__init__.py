"""Student-facing routes grouped by interface."""

from .blueprint import student_bp

from . import dashboard  # noqa: F401,E402
from . import timeline  # noqa: F401,E402
from . import registration  # noqa: F401,E402
from . import submit  # noqa: F401,E402
from . import feedback  # noqa: F401,E402
from . import result  # noqa: F401,E402
from . import challenges  # noqa: F401,E402
from . import topbar  # noqa: F401,E402
from . import notifications  # noqa: F401,E402
from . import ai  # noqa: F401,E402
from . import profile  # noqa: F401,E402

__all__ = ["student_bp"]
