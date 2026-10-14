import os
import re
import pandas as pd


reference_grid_file_path = "data/drc_1km_grid_reference_table.csv"

csvs_folder = "data/gee/"

df = pd.read_csv(reference_grid_file_path)

reference_row_count = df.shape[0]

# Get neighboring pixels for each row
# Step 1: Compute row/col index
x0, y0 = df['x_native'].min(), df['y_native'].min()
df['col'] = ((df['x_native'] - x0) // 1000).astype(int)
df['row'] = ((df['y_native'] - y0) // 1000).astype(int)

# Step 2: Build lookup from (row, col) to grid_id
pos_to_id = dict(zip(zip(df['row'], df['col']), df['grid_id']))

# Step 3: Define function to find neighbors
def get_neighbors(row, col):
    offsets = [(-1, -1), (-1, 0), (-1, 1),
               (0, -1),          (0, 1),
               (1, -1), (1, 0),  (1, 1)]
    neighbors = []
    for dr, dc in offsets:
        neighbor_pos = (row + dr, col + dc)
        if neighbor_pos in pos_to_id:
            neighbors.append(pos_to_id[neighbor_pos])
    return neighbors

# Step 4: Apply to dataframe
df['neighbors'] = df.apply(lambda r: get_neighbors(r['row'], r['col']), axis=1)



# Some variables are too large for a single GEE export task and get split
# into several "<name>_batchN" files instead — each covering the SAME grid
# cells but a different subset of the underlying source data (e.g. bird
# species richness batched by species group, since the species count for
# a cell is additive across batches). These need to be summed together per
# grid_id into one column, not merged in as separate columns.
BATCH_COLUMN_PATTERN = re.compile(r'^(.+)_batch\d+$')

# Maps a batch base name (column name with "_batchN" stripped) to the
# canonical column name expected by the optimization configs, for cases
# where they differ. Add an entry here for any future batched variable whose
# stripped base name doesn't already match its expected final column name.
BATCH_COLUMN_RENAMES = {
    'bird_richness': 'bird_species_richness',
}

batch_groups = {}   # base_name -> list of (file_name, pandas.Series indexed by grid_id)
regular_files = []  # list of (file_name, DataFrame)

for file_name in sorted(os.listdir(csvs_folder)):
    if not file_name.endswith(".csv"):
        continue

    file_path = os.path.join(csvs_folder, file_name)
    data_df = pd.read_csv(file_path)

    # Check that file has exactly 2 columns and one of them is 'grid_id'
    if 'grid_id' not in data_df.columns or len(data_df.columns) != 2:
        print(f"Skipping {file_name}: unexpected columns.")
        continue

    value_col = [c for c in data_df.columns if c != 'grid_id'][0]
    match = BATCH_COLUMN_PATTERN.match(value_col)

    if match:
        base_name = match.group(1)
        batch_groups.setdefault(base_name, []).append(
            (file_name, data_df.set_index('grid_id')[value_col])
        )
    else:
        regular_files.append((file_name, data_df))

# Merge regular (non-batched) variables
for file_name, data_df in regular_files:
    # Check if number of rows matches reference
    if data_df.shape[0] != reference_row_count:
        print(f"Skipping {file_name}: row count {data_df.shape[0]} does not match reference ({reference_row_count}).")
        continue

    df = df.merge(data_df, on='grid_id', how='left')
    print(f"Successfully joined {file_name} to the reference table")

# Sum and merge batched variables
for base_name, parts in batch_groups.items():
    column_name = BATCH_COLUMN_RENAMES.get(base_name, base_name)
    part_names = [file_name for file_name, _ in parts]
    series_list = [series for _, series in parts]

    combined = pd.concat(series_list, axis=1)
    if combined.isna().any().any():
        print(f"Warning: {column_name} batches ({', '.join(part_names)}) do not all cover the same grid_id set; missing values treated as 0.")
    batch_df = combined.fillna(0).sum(axis=1).rename(column_name).reset_index()

    if batch_df.shape[0] != reference_row_count:
        print(f"Skipping {column_name}: combined row count {batch_df.shape[0]} does not match reference ({reference_row_count}).")
        continue

    df = df.merge(batch_df, on='grid_id', how='left')
    print(f"Successfully summed {len(parts)} batch file(s) ({', '.join(part_names)}) into '{column_name}' and joined to the reference table")

# Save output
os.makedirs("output", exist_ok=True)
output_path = "output/drc_1km_data_planning_units.csv"
df.to_csv(output_path, index=False)

