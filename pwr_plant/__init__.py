"""PWR two-point plant model."""
from .model import *          # noqa: F401,F403  -- flat API: from pwr_plant import Plant
from . import model           # noqa: F401       -- and pwr_plant.model stays reachable
