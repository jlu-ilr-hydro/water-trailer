
import yaml

from .base import Bus
from .addupi import AddUPIBus
from .sdi12 import SDI12bus
bus_available = {'addupi': AddUPIBus,
                 'sdi12': SDI12bus}

def read(filename: str):
    with open(filename) as f:
        data = yaml.load(f)
