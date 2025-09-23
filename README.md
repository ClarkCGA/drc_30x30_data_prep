
# Spatial Data Preparation - DRC 30 x 30 Planning

This repository provides a Python implementation of a geospatial analysis workflow using the Google Earth Engine (GEE) Python API. It computes grid-level summary statistics for various environmental and land cover datasets in the Democratic Republic of the Congo (DRC), exporting the results to CSV.

## 🔧 Project Structure

```
drc_30x30_data_prep/
├── Dockerfile
├── authenticate.ipynb
├── requirements.txt
├── README.md
└── gee_grid_analysis/
    ├── __init__.py
    ├── datasets.py
    ├── utils.py
└── scripts/
    ├── gee_export.py
    ├── merge_tables.py
└── data/
    ├── drc_1km_grid_reference_table.csv
```

## Requirements

### Software
This toolbox is developed in Python. To ensure reproducibility of results, the tool is wrapped in a Docker environment. To run the code locally, you need to install [Docker](https://www.docker.com/products/docker-desktop/) for free and follow the instructions below. 

If you are running this on Windows, it's recommended to run it inside Windows Subsystem for Linux (WSL). Follow the instructions [here](https://learn.microsoft.com/en-us/windows/wsl/install) to enable WSL in your Windows. 

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone git@github.com:ClarkCGA/drc_30x30_data_prep.git
cd drc_30x30_data_prep
```

## 🐳 Running with Docker


### 2. Build the Docker Image

```bash
docker build -t drc-30x30-data-prep .
```

### 3. Run the Docker container

```bash
docker run -it -p 8888:8888 drc-30x30-data-prep
```
This will print out the URL to the Jupyter Lab (including its token). Copy the URL, and paste into a browser to launch Jupyter Lab. 

### 4. Authenticate with GEE

Open `authenticate.ipynb` and run the two cells to authenticate with your GEE account in the Docker container. 

### 5. Export Data from GEE

Open terminal in Jupyter Lab, and run the following to export all the data from GEE:

```bash
python scripts/gee_export.py
```

### 6. Add Neighborhood Information

Move all the exported CSV files to `data/gee`, and run the following:

```bash
python scripts/merge_tables.py
```

## ⚙️ Customization

To use a service account or change datasets or export parameters, modify:

- `gee_grid_analysis/datasets.py`
- `gee_grid_analysis/utils.py`
- `run_analysis.py`


## 📤 Output

All exports are sent to your Google Drive, in the folder named `GEE_Downloads`. You can monitor progress in the [Earth Engine Tasks tab](https://code.earthengine.google.com/tasks).


## Acknowledgements
This project is funded by the Wildlife Conservation Society (WCS) through a contract with Clark CGA. 