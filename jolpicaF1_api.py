from urllib.parse import urlunsplit, urlencode
import os
import json
import time
import requests
import pandas as pd
import re 

SCHEME = "http"
BASE = "api.jolpi.ca"
PATH = "/ergast/f1"

SLEEP = 0.35 #wait time for rate limiting
CACHE_DIR = "cache_pitstops"
CACHE_DRIVERS_DIR = "cache_drivers"

DRIVER_NAME_TO_ID = {
    "Lewis Hamilton": "hamilton",
    "George Russell": "russell",
    "Valtteri Bottas": "bottas",
    "Max Verstappen": "max_verstappen",
    "Sergio Pérez": "perez",
    "Charles Leclerc": "leclerc",
    "Carlos Sainz": "sainz",
    "Sebastian Vettel": "vettel",
    "Lando Norris": "norris",
    "Daniel Ricciardo": "ricciardo",
    "Oscar Piastri": "piastri",
    "Fernando Alonso": "alonso",
    "Esteban Ocon": "ocon",
    "Pierre Gasly": "gasly",
    "Lance Stroll": "stroll",
    "Sebastian Vettel": "vettel",
    "Yuki Tsunoda": "tsunoda",
    "Nyck de Vries": "de_vries",
    "Daniel Ricciardo": "ricciardo",
    "Kimi Räikkönen": "raikkonen",
    "Antonio Giovinazzi": "giovinazzi",
    "Zhou Guanyu": "zhou",
    "Valtteri Bottas": "bottas",
    "Kevin Magnussen": "kevin_magnussen",
    "Romain Grosjean": "grosjean",
    "Mick Schumacher": "mick_schumacher",
    "Nico Hülkenberg": "hulkenberg",
    "George Russell": "russell",
    "Nicholas Latifi": "latifi",
    "Alexander Albon": "albon",
    "Logan Sargeant": "sargeant",
    "Robert Kubica": "kubica",
    "Liam Lawson": "lawson",
    "Franco Colapinto": "colapinto",
    "Jack Aitken": "aitken",
    "Pietro Fittipaldi": "fittipaldi",
    }  


def build_api_url(endpoint_path, query_dict=None):
    """
    Builds a full URL for an API call by combining
    the endpoint and the query parameters.

    Args:
        - endpoint_path (str): API endpoint path.
        - query_dict (dict, optional): dictionary with the query parameters.

    Returns:
        - url (str): full URL ready for the request.
    """
    if query_dict is None:
        query_dict = {}

    query = urlencode(query_dict)
    full_path = f"{PATH.rstrip('/')}/{endpoint_path.lstrip('/')}"

    return urlunsplit((SCHEME, BASE, full_path, query, ""))



def all_pitstops_in(start_year, end_year):
    """
    Downloads and aggregates every Formula 1 pit stop in a range of years
    from the API, with a local cache and rate-limit handling.

    Args:
        - start_year (int): first year of the range.
        - end_year (int): last year of the range.

    Returns:
        - all_pitstops (list[dict]): list of dictionaries with the information
          of every pit stop recorded in the given period.
    """

    os.makedirs(CACHE_DIR, exist_ok=True)
    all_pitstops = []

    for year in range(start_year, end_year + 1):
        round_number = 1
        empty = 0

        while True:
            cache_file = os.path.join(CACHE_DIR, f"{year}_{round_number}.json")

            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                url = build_api_url(f"/{year}/{round_number}/pitstops/", {"limit": 100, "offset": 0})

                while True:
                    r = requests.get(url, timeout=20)

                    if r.status_code == 429:
                        time.sleep(2)
                        continue

                    if r.status_code != 200:
                        data = None
                        break

                    data = r.json()
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(data, f)

                    time.sleep(SLEEP)
                    break

                if data is None:
                    break

            races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])

            if not races:
                empty += 1
                if empty > 0:
                    break
                round_number += 1
                continue

            empty = 0

            race = races[0]
            pit_list = race.get("PitStops") or race.get("Pitstops") or []

            for ps in pit_list:
                all_pitstops.append({
                    "season": year,
                    "round": round_number,
                    "raceName": race.get("raceName"),
                    "date": race.get("date"),
                    "driverId": ps.get("driverId"),
                    "lap": ps.get("lap"),
                    "stop": ps.get("stop"),
                    "time": ps.get("time"),
                    "duration": ps.get("duration"),
                })

            round_number += 1

    return all_pitstops



def driverid_to_number(start_year, end_year):
    """
    Builds a mapping between driverId and the drivers' permanent number
    for each season within a range of years, using the API
    and a local cache to reduce calls.

    Args:
        - start_year (int): first year of the range.
        - end_year (int): last year of the range.

    Returns:
        - mapping_drivers (dict): dictionary with the structure
          {year: {driverId: permanentNumber}} for each season.
    """

    os.makedirs(CACHE_DRIVERS_DIR, exist_ok=True)

    mapping_drivers = {}  # year -> {driverId: number}

    for year in range(start_year, end_year + 1):
        cache_file = os.path.join(CACHE_DRIVERS_DIR, f"{year}_drivers.json")

        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            url = build_api_url(f"/{year}/drivers/", {"limit": 100, "offset": 0})

            while True:
                r = requests.get(url, timeout=20)

                if r.status_code == 429:
                    print("Too many requests, error 429")
                    time.sleep(2)
                    continue

                r.raise_for_status()
                data = r.json()

                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)

                time.sleep(SLEEP)
                break

        drivers = data.get("MRData", {}).get("DriverTable", {}).get("Drivers", [])

        mapping_drivers[year] = {}
        for d in drivers:
            driver_id = d.get("driverId")
            number = d.get("permanentNumber")
            if driver_id and number:
                mapping_drivers[year][driver_id] = int(number)

    return mapping_drivers


def write_pitstops_csvs(pitstops, mapping_drivers, base_dir="data"):
    """
    Builds and saves one CSV per race with aggregated pit stop statistics,
    including the number of stops and the median stop duration per driver.

    Args:
        - pitstops (list[dict]): list of pit stop records (one per stop) obtained from the API.
        - mapping_drivers (dict): dictionary {year: {driverId: permanentNumber}} used to assign DriverNumber.
        - base_dir (str): base directory where the generated CSVs are saved.
    """
    df = pd.DataFrame(pitstops)

    # duration to numeric
    df["duration"] = pd.to_numeric(df["duration"], errors="coerce")

    # add the driver number
    df["DriverNumber"] = df.apply(lambda x: mapping_drivers.get(x["season"], {}).get(x["driverId"]), axis=1)

    df_agg = (df.groupby(["season", "round", "driverId", "DriverNumber"]).agg(
              NPitstops=("duration", "count"),
              MedianPitStopDuration=("duration", "median"))
            .reset_index()
            .rename(columns={"driverId": "DriverId"}))

    # write one CSV per race
    for (season, round), sub in df_agg.groupby(["season", "round"], sort=True):
        year_dir = os.path.join(base_dir, str(season))
        os.makedirs(year_dir, exist_ok=True)

        out_path = os.path.join(year_dir, f"round_{round}_API.csv")
        sub[["DriverId", "DriverNumber", "NPitstops", "MedianPitStopDuration"]].to_csv(out_path, index=False)



def build_merged_dataset(data_root="data", year_start=2019, year_end=2024, out_csv=None):
    """
    Builds a combined dataset per season and race, joining the scraped CSVs
    (web data) with the CSVs generated from the API (pit stops), and optionally saves it.

    Args:
        - data_root (str): root directory with one folder per year holding the CSVs.
        - year_start (int): first year (included) to process.
        - year_end (int): last year (included) to process.
        - out_csv (str, optional): output path if the final dataset should be saved as CSV.

    Returns:
        - big_df (DataFrame): final dataframe with every season and race merged.
    """
    all_rows = []

    for year in range(year_start, year_end + 1):
        year_dir = os.path.join(data_root, str(year))
        if not os.path.isdir(year_dir):
            continue

        files = os.listdir(year_dir)

        race_files = {}
        for f in files:
            m = re.match(r"^(\d{2})_.*\.csv$", f)
            if m:
                round = int(m.group(1))
                race_files[round] = os.path.join(year_dir, f)

        api_files = {}
        for f in files:
            m = re.match(r"^round_(\d+)_API\.csv$", f)
            if m:
                round = int(m.group(1))
                api_files[round] = os.path.join(year_dir, f)

        common_rounds = sorted(set(race_files) & set(api_files))

        for round in common_rounds:
            df_web = pd.read_csv(race_files[round])
            df_api = pd.read_csv(api_files[round])

            df_web["Driver"] = df_web["Driver"].map(DRIVER_NAME_TO_ID)

            df_merged = df_web.merge(df_api, left_on="Driver", right_on="DriverId", how="inner")

            df_merged["Season"] = year
            df_merged["RaceNumber"] = round
            df_merged["NPitstops"] = df_merged["NPitstops"].fillna(0)

            all_rows.append(df_merged)

    big_df = pd.concat(all_rows, ignore_index=True)
    cols_to_drop = ["Laps1", "Lapsa", "Start", "Unnamed: 8"]

    big_df = big_df.drop(columns=cols_to_drop, errors="ignore")

    if out_csv:
        big_df.to_csv(out_csv, index=False)

    return big_df




