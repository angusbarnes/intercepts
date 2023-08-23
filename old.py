import csv
import ElementParser
import KnownElements
from Hole import AssayType, AssayUnit

data_table = {}

with open('samples.csv', newline='') as csvfile:
    spamreader = csv.reader(csvfile, delimiter=',', quotechar='"')
    for row in spamreader:

        if row[1] not in data_table:
            data_table[row[1]] = []

        data_table[row[1]].append(row)

print(f"Found {len(data_table)} holes in CSV")

header_row = data_table["Hole number"]
header_lookup = {}
for i, header in enumerate(header_row[0]):
    header_lookup[header] = i
    assay = ElementParser.TryParse(header)

    unit_type = None

    if assay:
        element, unit = assay

        type = None
        unit = unit.lower()

        if unit == "ppm":
            unit_type = AssayType(element, AssayUnit.PPM)
        elif unit == "ppb":
            unit_type = AssayType(element, AssayUnit.PPB)
        elif unit == "ppt":
            unit_type = AssayType(element, AssayUnit.PPT)
        elif unit == "%":
            unit_type = AssayType(element, AssayUnit.Percent)
        else: raise ValueError("Unsupported Unit Present: " + unit)


get_index = lambda x: header_lookup[x]

focus_hole = data_table["CANDD017"]

def is_contiguous(row, next):
    return row[3] == next[2]

def group_contiguous_intervals(intervals):
    groups = []
    current_group = []

    for interval in intervals:
        if not current_group:
            current_group.append(interval)
        else:
            last_interval = current_group[-1]
            if last_interval[3] == interval[2]:
                current_group.append(interval)
            else:
                groups.append(current_group)
                current_group = [interval]

    if current_group:
        groups.append(current_group)

    return groups

focus_hole.sort(key = lambda x: float(x[2]))

groups = group_contiguous_intervals(focus_hole)

def remove_tail_below_threshold(array, threshold):
    tail_length = 0

    # Find the length of the tail with values below the threshold
    for value in reversed(array):
        if value < threshold:
            tail_length += 1
        else:
            break

    # Remove the tail from the array
    if tail_length == 0: return array

    array = array[:-tail_length]
    return array

def group_values(array, cutoff):
    groups = []
    current_group = []
    current_gaps  = 0
    collecting = False
    # Iterate through the array
    for row in array:
        value = float(row[get_index("Cu ppm")])
        # Check if the value is below the cutoff
        if value >= cutoff:
            
            # Check if the current group is empty or has less than two wildcard values
            if not current_group or current_gaps < 2:
                current_group.append(value)
                collecting = True
            else:
                # Add the current group to the list of groups and start a new group
                groups.append(remove_tail_below_threshold(current_group, 0.1))
                current_group = [value]
                collecting = False
                current_gaps = 0
        elif collecting:
            # Add the value to the current group if it's a wildcard value
            current_group.append(value)
            current_gaps += 1
        else: continue

    # Add the last group to the list of groups
    if current_group:
        groups.append(remove_tail_below_threshold(current_group, 0.1))

    return groups

test_groups = []
for group in groups:
    test_groups += group_values(group, 0.1)

print(f"Found {len(test_groups)} intervals:")
for intercept in test_groups:
    distance = 0
    concentration = 0
    for value in intercept:
        distance += 1
        concentration += value
    print(f"{distance}m at {concentration/distance:.2f}% from UNKNOWN m")
    print(intercept)