# Global Magnet API Validation Studies

This repository contains validation studies for Amentum's Global Magnet API available [here](https://amentum.space/globalmagnet)

Each directory contains:

- a README.md file with a description of the study, 
- instructions to download data files and run the Python code to regenerate the results, and
- images comparing values of the magnetic declination measured and calculated using Amentum's API. 

# Running the analyses 

Follow the instructions in the README file to fetch the validation data and to run the analysis script.

Install the necessary Python packages included in the requirements.txt file:

    pip install -r requirements.txt 

(if you are using pip).  

Then run the analysis script using the following:

    python analysis.py <command line arguments>

The specific <command line arguments> will be different for each study.

That will launch a browser window and display the interactive plots. 

Copyright 2021 [Amentum Aerospace](https://amentum.space), Australia.

