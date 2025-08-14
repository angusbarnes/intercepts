from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple
import hashlib

class AssayUnit(Enum):
    PPM = 1,
    PPB = 2,
    PPT = 3,
    Percent = 4
    GPT = 5
 
@dataclass
class AssayType:
    element: str
    base_unit: AssayUnit
    reported_unit: AssayUnit = None

    def __hash__(self) -> int:

        sha256_hash = hashlib.sha256((self.element + self.base_unit.name).encode('utf-8')).hexdigest()  # Calculate the SHA-256 hash
        return hash(self.element + self.base_unit.name)
    
    def __repr__(self) -> str:
        return f"<AssayType: {self.element} in {self.base_unit.name}>"
    
    def __str__(self) -> str:
        return f"{self.element} in {self.base_unit.name}"
    
    def get_unique_id(self):
        return self.__hash__()
    
    def convert_to_reported_unit(self, value):
        # Define conversion factors
        conversion_factors = {
            AssayUnit.PPM: 1,
            AssayUnit.PPB: 1000,
            AssayUnit.Percent: 10000,
            AssayUnit.GPT: 1
        }

        # Check if units are valid
        if self.base_unit not in conversion_factors or self.reported_unit not in conversion_factors:
            raise ValueError("Invalid units")
        
        if self.base_unit == self.reported_unit:
            return value

        # Convert to PPM
        ppm_value = value * conversion_factors[self.base_unit]

        # Convert from PPM to the desired unit
        result = ppm_value / conversion_factors[self.reported_unit]

        return result
    
    def reported_unit_text(self):
        text = {
            AssayUnit.PPM: 'ppm',
            AssayUnit.PPB: 'ppb',
            AssayUnit.Percent: '%',
            AssayUnit.GPT: 'g/t'
        }

        return text[self.reported_unit]
    
@dataclass
class Intercept:

    assay: AssayType
    concentration: float
    distance: float
    span: tuple[float, float]
    co_analytes: dict[AssayType, float]
    
    def get_unit_as_reported(self):
        return self.assay.reported_unit_text()
    
    def get_concentration_as_reported(self):
        return self.assay.convert_to_reported_unit(self.concentration)

    def to_string(self):
        return f"{self.distance:.2f}m @ {self.assay.convert_to_reported_unit(self.concentration):.2f}{self.assay.reported_unit_text()} {self.assay.element} from {self.span[0]:.0f}m"

@dataclass
class IntervalData:
    # A tuple represting the interval ranging from `start` to `end`
    span: Tuple[float, float]

    assay_data: dict[int, float]
    ''' Represents a dictionary of each assay type recorded for this interval'''

    def start(self) -> float:
        return self.span[0]
    
    def end(self) -> float:
        return self.span[1]
    
    def get_length(self):
        return self.span[1] - self.span[0]
    
    def get_assay(self, assay_type: AssayType):
        #print(f"Assay Type Requested: {type}")
        if assay_type.get_unique_id() in self.assay_data:
            return self.assay_data[assay_type.get_unique_id()]
        
        return None

    def __repr__(self) -> str:
        try:
            return f"<Interval: ({self.span} @ {self.assay_data[AssayType('Cu', AssayUnit.Percent).get_unique_id()]})>"
        except:
            return f"<Interval ({self.span} @ NaN)>"
    
    def calculate_concentration_metres(self, assay: AssayType):
        return self.assay_data[assay.get_unique_id()] * self.get_length()

@dataclass
class HoleData:
    holeID: str
    intervals: List[IntervalData] = None

    def add(self, interval: IntervalData):

        if not self.intervals:
            self.intervals = []

        self.intervals.append(interval)

    def get_intervals(self):
        if not self.intervals:
            self.intervals = []

        return sorted(self.intervals, key = lambda x: x.start())
    
    def group_contiguous_intervals(self) -> List[List[IntervalData]]:
        groups = []
        current_group = []

        for interval in self.get_intervals():
            if not current_group:
                current_group.append(interval)
            else:
                last_interval = current_group[-1]
                if last_interval.end() == interval.start():
                    current_group.append(interval)
                else:
                    groups.append(current_group)
                    current_group = [interval]

        if current_group:
            groups.append(current_group)

        return groups