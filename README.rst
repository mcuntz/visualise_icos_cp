Visualise ICOS ecosystem data from the ICOS Carbon Portal (ICOS-CP)

usage: make_html.py [-h] [-d number_days] [-p product] [args]

Make visualisation for FR-Hes.

positional arguments:
  args                  ICOS Ecosystem station name

options:
  -h, --help            show this help message and exit
  -d number_days, --days number_days
                        Number of days to visualise. 0 means all available days
                        (default: 0).
  -p product, --product product
                        ICOS CP data product: "NRT" or "FLUXNET"
                        (default: NRT).

Examples
--------
# Visualise the last 30 days
  python make_html.py FR-Hes -d 30

History
-------
Written, May 2023, Matthias Cuntz
