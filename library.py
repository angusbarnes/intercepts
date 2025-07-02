
# Record the header fields of interest and cache their indexes so that they can be looked up
# in the csv rows efficiently
from typing import List
from Hole import *
import ElementParser
from config import config
from exceptions import MissingHoleDataException


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
            #logging.critical(f"WE HAVE NEGATIVE CONCENTRATIONS. {interval}")
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

from Hole import AssayType, AssayUnit, Intercept, IntervalData

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