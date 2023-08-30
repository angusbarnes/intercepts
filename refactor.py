import csv
import pickle
import traceback
from typing import List
import ElementParser
import KnownElements
from Hole import *
from config import config
import sys

import logging

log_level = logging.DEBUG

# if config.logging.log_level == "ERROR_ONLY":
#     log_level = logging.WARNING

# Configure the logging settings
logging.basicConfig(
    level=logging.DEBUG,    # Set the minimum level for logging messages
    format="%(asctime)s [%(levelname)s] %(message)s",  # Define the log message format
    handlers=[
        #logging.StreamHandler(),  # Send log messages to the console
        logging.FileHandler("app.log", mode = 'w')  # Save log messages to a file
    ]
)

# Custom exception handler function
def custom_exception_handler(exc_type, exc_value, exc_traceback):
    logging.error("An unhandled exception occurred:", exc_info=(exc_type, exc_value, exc_traceback))
    print("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
# Set the custom exception handler globally
sys.excepthook = custom_exception_handler

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
        raise MissingHoleDataException(csv_data[get_index(config.settings.hole_id_column_name)], f"No useable value for hole From and To values for sample ID: {csv_data[get_index(config.settings.sample_id_column_name)]}")

    assays = {}
    for key in header_cache:
        if type(key) == AssayType:
            # Map the detected AssayType to its old header string name in the CSV Row
            # if the value cannot be converted (IE it does not exist for this interval)
            # we do not add it
            try:      
                assays[key.get_unique_id()] = float(csv_data[get_index(key)])
                logging.debug(f"Key created for: {key.get_unique_id()}")
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

def calculate_intercept(intercept_intervals: list[IntervalData], assay_type: AssayType, co_analytes):
    ''' 
    Calculate intercept takes a list of intervals and an assay type.
    Based on this information, it calculates the concentration of the specified assay
    across the total length of the intervals provided.

    Returns: an Intercept() object representing this intercept
    '''
    concentration = 0
    distance = 0
    coans = {}
    for co in co_analytes:
        coans[co.get_unique_id()] = 0

    for interval in intercept_intervals:
        concentration += interval.calculate_concentration_metres(assay_type)
        distance += interval.get_length()

        for co in co_analytes:
            try:
                coans[co.get_unique_id()] += interval.calculate_concentration_metres(co)
            except: continue

    return Intercept(assay_type,  concentration/distance, distance, intercept_intervals[0].span, coans)

# contiguous_intervals represent the contiguous subsections of a hole
def calculate_intercepts_from_group(contiguous_intervals: List[IntervalData], assay: AssayType, cutoff: float, co_analytes = None) -> List[List[IntervalData]]:
    groups = []
    current_group = []
    current_gaps  = 0
    collecting = False
    # Iterate through the array
    for interval in contiguous_intervals:

        value = interval.get_assay(assay)
        #print(f"Processing value: {value} from interval: {interval}")

        if value is not None and value < 0:
            logging.critical(f"WE HAVE NEGATIVE CONCENTRATIONS. {interval}")
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
                groups.append(calculate_intercept(remove_tail_below_threshold(current_group, assay, cutoff), assay, co_analytes))
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
        groups.append(calculate_intercept(remove_tail_below_threshold(current_group, assay, cutoff), assay, co_analytes))

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
    
    return line_count, hasher.hexdigest()

def convert_unit(value, from_unit, to_unit):
    # Define conversion factors
    conversion_factors = {
        AssayUnit.PPM: 1,
        AssayUnit.PPB: 1000,
        AssayUnit.Percent: 10000,
        AssayUnit.GPT: 1
    }

    # Check if units are valid
    if from_unit not in conversion_factors or to_unit not in conversion_factors:
        raise ValueError("Invalid units")

    # Convert to PPM
    ppm_value = value * conversion_factors[from_unit]

    # Convert from PPM to the desired unit
    result = ppm_value / conversion_factors[to_unit]

    return result

def unit_text_to_type(unit: str):
    Unit = AssayUnit.PPM
    unit = unit.lower()
    if unit == '%':
        Unit = AssayUnit.Percent
    elif unit == 'ppm':
        Unit = AssayUnit.PPM
    elif unit == 'ppb':
        Unit = AssayUnit.PPB
    elif unit == 'g/t':
        Unit = AssayUnit.GPT
    else:
        raise ValueError(f"Error when loading co-analytes. Unsupported unit of type: {unit}")
    
    return Unit

def try_parse_to_assay_type(element: str, base_unit: str, reported_unit: str):

    base = unit_text_to_type(base_unit)
    reported = unit_text_to_type(reported_unit)

    return AssayType(element, base, reported)

from tqdm import tqdm
import os

if '-recalc' in sys.argv:
    config.settings.recalc = True
else:
    config.settings.recalc = False



Unit = AssayUnit.PPM
if config.assays[0]['base_unit'].lower() == '%':
    Unit = AssayUnit.Percent
ASSAY_UNIT_SELECT = AssayType(config.assays[0]['element'], Unit)
print(f"Selected unit: {config.assays[0]['element']} in {Unit}")

header_cache = {}
data_table: dict[int, HoleData] = {}

file_name = config.settings.exported_data_path
cache_location = config.settings.cache_location

loc, hash_value = count_lines_and_hash(file_name)

if config.settings.recalc == False and os.path.exists(f"{cache_location}/{str(hash_value)}.dat"):
    file = open(f"{cache_location}/{str(hash_value)}.dat", 'rb')
    data_table = pickle.load(file)
    file.close()
else:
    with open(file_name, newline='') as csvfile:
        spamreader = csv.reader(csvfile, delimiter=',', quotechar='"')

        header_row = next(spamreader) # Read the first line of the header file
        header_cache = create_header_cache(header_row, ['From', 'To', config.settings.hole_id_column_name, config.settings.sample_id_column_name])
        #print(header_cache)

        # we use loc - 1 to account for the header row int the csv
        for row in tqdm(spamreader, unit='Samples', total=loc - 1):

            holeID = row[header_cache[config.settings.hole_id_column_name]]
            if holeID not in data_table:
                logging.debug(f"Found hole with ID: {holeID}")
                data_table[holeID] = HoleData(holeID)

            interval = None
            try:
                interval = construct_interval_from_csv_row(row, header_cache)
            except MissingHoleDataException as err:
                continue
            data_table[holeID].add(interval)
        
        # open a file, where you ant to store the data
        file = open(f"{cache_location}/{str(hash_value)}.dat", 'wb')

        # dump information to that file
        pickle.dump(data_table, file)

        # close the file
        file.close()

print(f"Found {len(data_table)} holes in CSV")

assay_list = []
for assay in config.assays:
    element = assay['element']
    base_unit = assay['base_unit']
    reported_unit = assay['reported_unit']
    cutoffs = assay['cutoffs']
    
    primary = try_parse_to_assay_type(element, base_unit, reported_unit)

    co_analytes = assay['co_analytes']
    analytes = []
    for co in co_analytes:
        analytes.append(try_parse_to_assay_type(co['element'], co['base_unit'], co['reported_unit']))

    assay_list.append((primary, cutoffs, analytes))

print(assay_list)
cutoffs = [0.1, 0.5, 1]
import time
current_time = time.strftime('%H-%M-%S')  # Current timestamp as YYYYMMDDHHMMSS
filename = f'intercepts_{current_time}.csv'

test_dict = {hash(ASSAY_UNIT_SELECT): 'it works'}

with open(filename, mode='w', newline='') as csvfile:
    writer = csv.writer(csvfile)

    header = ['Hole', 'Primary Assay',  'From', 'To', 'Cutoff', 'Primary Intercept', 'Co-analytes']
    writer.writerow(header)

    for hole in tqdm(data_table):
        focus_hole = data_table[hole]

        # Get a list containing groups of intervals which are contiguous in this hole
        # This simply is a list of sections from the hole which have contiguous data
        contiguous_interval_groups = focus_hole.group_contiguous_intervals()

        for grouped_interval in contiguous_interval_groups:

            # Get all intervals from the hole which are contiguous and are above a specified cutoff
            # This takes a list of intervals which are contigious and returns all subgroups of this interval
            # that match the filtering criteria. This means that we end up with a list of lists
            for assay, cutoffs, coans in assay_list:
                for cutoff in cutoffs:
                    intercepts = calculate_intercepts_from_group(grouped_interval, assay, cutoff, coans)

                    # Here the intercept variable represents a list of IntervalData which have been judged to be both
                    # contiguous and above the cutoff threshold
                    for intercept in intercepts:
                        #inter = calculate_intercept(intercept, ASSAY_UNIT_SELECT)
                        
                        co_string = ""
                        for co in coans:
                            co_string += f"{co.element}: {intercept.co_analytes[co.get_unique_id()]/intercept.distance:.2f} {co.base_unit.name},  "
                        writer.writerow([
                            hole, assay.element, 
                            intercept.span[0], intercept.span[0] + intercept.distance, 
                            f"{cutoff} {assay.base_unit.name} {assay.element}", intercept.to_string(),
                            co_string
                        ])