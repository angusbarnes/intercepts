from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple

class AssayUnit(Enum):
    PPM = 1,
    PPB = 2,
    PPT = 3,
    Percent = 4
 
@dataclass
class AssayType:
    element: str
    base_unit: AssayUnit

    def __hash__(self) -> int:
        return hash(self.element + self.base_unit.name)
    
    def __repr__(self) -> str:
        return f"<AssayType: {self.element} in {self.base_unit.name}>"
    
    def __str__(self) -> str:
        return f"{self.element} in {self.base_unit.name}"

@dataclass
class IntervalData:
    # A tuple represting the interval ranging from `start` to `end`
    span: Tuple[float, float]

    assay_data: dict[AssayType, float]
    ''' Represents a dictionary of each assay type recorded for this interval'''

    def start(self) -> float:
        return self.span[0]
    
    def end(self) -> float:
        return self.span[1]
    
    def get_length(self):
        return self.span[1] - self.span[0]
    
    def get_assay(self, type: AssayType):
        #print(f"Assay Type Requested: {type}")
        if type in self.assay_data:
            return self.assay_data[type]
        
        return None

    def __repr__(self) -> str:
        try:
            return f"<Interval ({self.span} @ {self.assay_data[AssayType('Cu', AssayUnit.Percent)]})>"
        except:
            return f"<Interval ({self.span} @ NaN)>"
    
    def calculate_concentration_metres(self, assay: AssayType):
        return self.assay_data[assay] * self.get_length()

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
    
    def group_contiguous_intervals(self) -> List[IntervalData]:
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