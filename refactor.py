import csv
import pickle
from typing import List
import ElementParser
import KnownElements
from Hole import AssayType, AssayUnit, HoleData, IntervalData
from config import config

class MissingHoleDataException(Exception):
    def __init__(self, hole_id, message=None):
        self.hole_id = hole_id
        self.message = message
        super().__init__(self.get_exception_message())

    def get_exception_message(self):
        if self.message:
            return f"Missing data for HoleID {self.hole_id}: {self.message}"
        else:
            return f"Missing data for HoleID {self.hole_id}"

# Record the header fields of interest and cache their indexes so that they can be looked up
# in the csv rows efficiently
def create_header_cache(header_row: List[str], fields_to_cache: List[str]):
    cache = {}
    for index, header in enumerate(header_row):
        
        if header in fields_to_cache:
            cache[header] = index
        elif assay := ElementParser.TryParse(header):
            element, unit = assay
            unit = unit.lower()
            unit_type = None
            if unit == "ppm":
                unit_type = AssayType(element, AssayUnit.PPM)
            elif unit == "ppb":
                unit_type = AssayType(element, AssayUnit.PPB)
            elif unit == "ppt":
                unit_type = AssayType(element, AssayUnit.PPT)
            elif unit == "%":
                unit_type = AssayType(element, AssayUnit.Percent)
            else: raise ValueError("Unsupported Unit Present: " + unit)

            cache[unit_type] = index
            print(f"Cached Unit: {unit_type}")
        
    return cache

def construct_interval_from_csv_row(csv_data: str, header_cache: dict):
    get_index = lambda x: header_cache[x]
    span = (0, 0)
    try:
        span = (float(csv_data[get_index('From')]), float(csv_data[get_index('To')]))
    except ValueError as err:
        raise MissingHoleDataException(csv_data[get_index(config.settings.hole_id_column_name)], f"No useable value for hole From and To values for sample ID: {csv_data[get_index('SampleID')]}")

    assays = {}
    for key in header_cache:
        if type(key) == AssayType:
            # Map the detected AssayType to its old header string name in the CSV Row
            # if the value cannot be converted (IE it does not exist for this interval)
            # we do not add it
            try:      
                assays[key] = float(csv_data[get_index(key)])
                #print(f"Inserting Value: {csv_data[get_index(key)]} into key: {key}, for hole: {csv_data[get_index('Hole number')]}")
            except ValueError:
                continue

    if assays == {}:
        raise MissingHoleDataException(csv_data[get_index(config.settings.hole_id_column_name)], f"No assay data recorded for sample ID: {csv_data[get_index(config.settings.sample_id_column_name)]}")
    return IntervalData(span, assays)

def remove_tail_below_threshold(array, assay, threshold):
    tail_length = 0

    # Find the length of the tail with values below the threshold
    for interval in reversed(array):
        if not (c := interval.get_assay(assay)) or c < threshold:
            tail_length += 1
        else: break

    # Remove the tail from the array
    if tail_length == 0: return array

    array = array[:-tail_length]
    return array

# contiguous_intervals represent the contiguous subsections of a hole
def group_values(contiguous_intervals: List[IntervalData], assay: AssayType, cutoff) -> List[List[IntervalData]]:
    groups = []
    current_group = []
    current_gaps  = 0
    collecting = False
    # Iterate through the array
    for interval in contiguous_intervals:

        value = interval.get_assay(assay)
        #print(f"Processing value: {value} from interval: {interval}")

        if value is not None and value < 0:
            #print("WE HAVE NEGATIVE CONCENTRATIONS")
            pass

        if value == None:
            collecting = False
            value = -1 #FIXME: This could somehow cause some cursed bugs

        # Check if the value is below the cutoff
        if value >= cutoff:
            
            # Check if the current group is empty or has less than two wildcard values
            if not current_group or current_gaps <= 2:
                current_group.append(interval)
                collecting = True
                #print("decision 1 was made for value")
            else:
                # Add the current group to the list of groups and start a new group
                groups.append(remove_tail_below_threshold(current_group, assay, 0.1))
                current_group = [interval]
                collecting = True
                current_gaps = 0
                #print("decision 2 was made for value")
        elif collecting:
            # Add the value to the current group if it's a wildcard value
            current_group.append(interval)
            current_gaps += 1
            #print("decision 3 was made for value")
        else: continue

    # Add the last group to the list of groups
    if current_group:
        groups.append(remove_tail_below_threshold(current_group, assay, 0.1))

    return groups

import hashlib

def count_lines_and_hash(file_name):
    """
    Count the number of lines in a file and calculate its hash.
    
    Args:
        file_name (str): Path to the file.
        
    Returns:
        tuple: Number of lines and hash value.
    """
    line_count = 0
    hasher = hashlib.sha256()
    chunk_size = 8192
    
    with open(file_name, 'rb') as file:
        while chunk := file.read(chunk_size):
            line_count += chunk.count(b'\n')
            hasher.update(chunk)
    
    return line_count+1, hasher.hexdigest()

from tqdm import tqdm
import os

HOLE_ID_COLUMN_NUMBER = 1
ASSAY_UNIT_SELECT = AssayType('Cu', AssayUnit.Percent)

header_cache = {}
data_table: dict[str, HoleData] = {}

file_name = config.settings.exported_data_path
cache_location = config.settings.cache_location

loc, hash = count_lines_and_hash(file_name)

if os.path.exists(f"{cache_location}/{str(hash)}.dat"):
    file = open(f"{cache_location}/{str(hash)}.dat", 'rb')
    data_table = pickle.load(file)
    file.close()
else:
    with open(file_name, newline='') as csvfile:
        spamreader = csv.reader(csvfile, delimiter=',', quotechar='"')

        header_row = next(spamreader) # Read the first line of the header file
        header_cache = create_header_cache(header_row, ['From', 'To', 'SampleID', 'Hole number'])
        #print(header_cache)

        for row in tqdm(spamreader, unit='Samples', total=loc):

            holeID = row[HOLE_ID_COLUMN_NUMBER]
            if holeID not in data_table:
                #print(f"Found hole with ID: {holeID}")
                data_table[holeID] = HoleData(holeID)

            interval = None
            try:
                interval = construct_interval_from_csv_row(row, header_cache)
            except MissingHoleDataException as err:
                #print("NOTICE: " + err.get_exception_message())
                continue
            data_table[holeID].add(interval)
        
        # open a file, where you ant to store the data
        file = open(f"{cache_location}/{str(hash)}.dat", 'wb')

        # dump information to that file
        pickle.dump(data_table, file)

        # close the file
        file.close()

print(f"Found {len(data_table)} holes in CSV")

file = open("result.log", 'w')


def calculate_intercept(grouped_intervals: list[list[IntervalData]], assay_type: AssayType):
    for intercept in grouped_intervals:
        concentration = 0
        distance = 0
        for interval in intercept:
            concentration += interval.calculate_concentration_metres(assay_type)
            distance += interval.get_length()

for hole in tqdm(data_table):
    focus_hole = data_table[hole]

    groups = focus_hole.group_contiguous_intervals()

    test_groups = []
    for group in groups:
        test_groups += group_values(group, ASSAY_UNIT_SELECT, 0.1)

    #print(f"Found {len(test_groups)} intervals:")

    for intercept in test_groups:
        concentration = 0
        distance = 0
        for interval in intercept:
            concentration += interval.calculate_concentration_metres(ASSAY_UNIT_SELECT)
            distance += interval.get_length()

        file.write((f"{hole}:   {distance}m at {concentration/distance:.2f} {ASSAY_UNIT_SELECT.base_unit.name} {ASSAY_UNIT_SELECT.element} from {intercept[0].start()} m\n"))

file.close()