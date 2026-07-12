"""Student-facing routes grouped by interface."""

from .blueprint import student_bp

from . import dashboard  
from . import timeline  
from . import registration  
from . import submit  
from . import feedback  
from . import result  
from . import challenges  
from . import topbar 
from . import notifications  
from . import ai 
from . import profile  

__all__ = ["student_bp"]
