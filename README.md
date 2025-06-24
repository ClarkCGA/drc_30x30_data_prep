
# GEE Grid Analysis

This repository provides a Python implementation of a geospatial analysis workflow using the Google Earth Engine (GEE) Python API. It computes grid-level summary statistics for various environmental and land cover datasets in the Democratic Republic of the Congo (DRC), exporting the results to CSV.

The original version was written in the GEE JavaScript API; this version uses a modular Python implementation and is fully containerized via Docker.

## 🔧 Project Structure

```
drc_30x30/
├── Dockerfile
├── authenticate.ipynb
├── requirements.txt
├── run_analysis.py
├── README.md
└── gee_grid_analysis/
    ├── __init__.py
    ├── datasets.py
    ├── utils.py
```

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone git@github.com:ClarkCGA/drc_30x30.git
cd drc_30x30
```

## 🐳 Running with Docker


### 2. Build the Docker Image

```bash
docker build -t drc-30x30 .
```

### 3. Run the Docker container

```bash
docker run -it -p 8888:8888 drc-30x30
```
This will print out the URL to the Jupyter Lab (including its token). Copy the URL, and paste into a browser to launch Jupyter Lab. 

### 4. Authenticate with Google Earth Engine

Open `authenticate.ipynb` and run the two cells to authenticate with your GEE account in the Docker container. 

### 5. Run the Analysis

Open terminal in Jupyter Lab, and run the analysis as following:

```bash
python run_analysis.py
```

## ⚙️ Customization

To use a service account or change datasets or export parameters, modify:

- `gee_grid_analysis/datasets.py`
- `gee_grid_analysis/utils.py`
- `run_analysis.py`


## 📤 Output

All exports are sent to your Google Drive, in the folder named `GEE_Downloads`. You can monitor progress in the [Earth Engine Tasks tab](https://code.earthengine.google.com/tasks).