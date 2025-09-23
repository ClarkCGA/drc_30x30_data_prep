import os
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



# Loop through and merge
for file_name in os.listdir(csvs_folder):
    if file_name.endswith(".csv"):
        file_path = os.path.join(csvs_folder, file_name)
        data_df = pd.read_csv(file_path)

        # Check that file has exactly 2 columns and one of them is 'grid_id'
        if 'grid_id' not in data_df.columns or len(data_df.columns) != 2:
            print(f"Skipping {file_name}: unexpected columns.")
            continue

        # Check if number of rows matches reference
        if data_df.shape[0] != reference_row_count:
            print(f"Skipping {file_name}: row count {data_df.shape[0]} does not match reference ({reference_row_count}).")
            continue

        # Merge with reference
        df = df.merge(data_df, on='grid_id', how='left')
        print(f"Successfully joined {file_name} to the reference table")

# Save output
output_path = "output/drc_1km_planning_units.csv"
df.to_csv(output_path, index=False)

