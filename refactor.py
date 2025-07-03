import csv
from typing import List
from Hole import *
from config import config
import sys
import tomllib
import logging
from tqdm import tqdm
import time

from exceptions import MissingHoleDataException, custom_exception_handler
from library import calculate_intercepts_from_group, construct_interval_from_csv_row, convert_unit, count_lines_and_hash, create_header_cache, try_parse_to_assay_type


def analyse_hole(hole, writer, data_table, assay_list):
    if hole not in data_table:
        print(f"Could not find hole: {hole} in provided data set")
        return

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
                        co_string += f"{co.convert_to_reported_unit(intercept.co_analytes[co.get_unique_id()])/intercept.distance:.2f}{co.reported_unit_text()} {co.element},  "

                    # header = ['Hole', 'Primary Analyte', 'Cutoff', 'Cutoff Unit', 'From', 'To', 'Interval', 'Primary Intercept', 'Intercept Label', 'Co Analytes']
                    writer.writerow([
                        hole, assay.element, intercept.assay.convert_to_reported_unit(cutoff), assay.reported_unit_text(),
                        intercept.span[0], intercept.span[0] + intercept.distance, intercept.distance,
                        round(intercept.get_concentration_as_reported(),3), intercept.to_string(),
                        co_string
                    ])


def perform_analysis(data_table, assay_list, filename, holes_to_calc):
    with open(filename, mode='w', newline='') as csvfile:
        writer = csv.writer(csvfile, quoting=csv.QUOTE_NONNUMERIC, escapechar='\\')

        header = ['Hole', 'Primary Analyte', 'Cutoff', 'Cutoff Unit', 'From', 'To', 'Interval', 'Primary Intercept', 'Intercept Label', 'Co Analytes']
        writer.writerow(header)

        for hole in holes_to_calc:
            analyse_hole(hole, writer, data_table, assay_list)



def build_data_table(file_name, loc, update_progress=None):
    data_table: dict[int, HoleData] = {}
    with open(file_name, newline='') as csvfile:
        spamreader = csv.reader(csvfile, delimiter=',', quotechar='"')

        header_row = next(spamreader) # Read the first line of the header file
        header_cache = create_header_cache(header_row, [config.settings.from_column_name, config.settings.to_column_name, config.settings.hole_id_column_name, config.settings.sample_id_column_name])
    #print(header_cache)

    # we use loc - 1 to account for the header row int the csv
        for row in spamreader:
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

            if update_progress:
                update_progress()
        
    return data_table


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

sys.excepthook = custom_exception_handler


if __name__ == "__main__":
    if '-recalc' in sys.argv:
        config.settings.recalc = True
    else:
        config.settings.recalc = False


    file_name = config.settings.exported_data_path

    loc, hash_value = count_lines_and_hash(file_name)

    data_table_ = build_data_table(file_name, loc)

    queries = None
    with open('queries.toml', 'rb') as queries_file:
        queries = tomllib.load(queries_file)

    assay_list_ = []
    for assay in list(queries.values()):
        element = assay['element']
        base_unit = assay['base_unit']
        reported_unit = assay['reported_unit']
        cutoffs = assay['cutoffs']
        
        primary = try_parse_to_assay_type(element, base_unit, reported_unit)

        for i, cutoff in enumerate(cutoffs):
            cutoffs[i] = convert_unit(cutoff, primary.reported_unit, primary.base_unit)

        co_analytes = assay['co_analytes']
        analytes = []
        for co in co_analytes:
            analytes.append(try_parse_to_assay_type(co['element'], co['base_unit'], co['reported_unit']))

        assay_list_.append((primary, cutoffs, analytes))

    print(assay_list_)

    current_time = time.strftime('%H-%M-%S')  # Current timestamp as YYYYMMDDHHMMSS
    filename = f'intercepts_{current_time}.csv'

    if config.settings.hole_selections == ['*']:
        holes_to_calc = list(data_table_.keys())
    else:
        holes_to_calc = config.settings.hole_selections

    print(list(data_table_.keys()))


    perform_analysis(data_table_, assay_list_, filename, holes_to_calc)