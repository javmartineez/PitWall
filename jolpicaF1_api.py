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

SLEEP = 0.35 #valor de espera para el rate-limiting
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
    Construye una URL completa para realizar una llamada a la API,
    combinando el endpoint y los parámetros de consulta.

    Args:
        - endpoint_path (str): ruta del endpoint de la API.
        - query_dict (dict, optional): diccionario con los parámetros de la query.

    Returns:
        - url (str): URL completa lista para realizar la petición.
    """
    if query_dict is None:
        query_dict = {}

    query = urlencode(query_dict)
    full_path = f"{PATH.rstrip('/')}/{endpoint_path.lstrip('/')}"

    return urlunsplit((SCHEME, BASE, full_path, query, ""))



def all_pitstops_in(start_year, end_year):
    """
    Descarga y agrega todos los pit stops de Fórmula 1 en un rango de años,
    utilizando la API, con sistema de caché local y control de rate limiting.

    Args:
        - start_year (int): año inicial del rango a consultar.
        - end_year (int): año final del rango a consultar.

    Returns:
        - all_pitstops (list[dict]): lista de diccionarios con la información
          de cada pit stop registrada en el periodo indicado.
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
    Construye un mapeo entre driverId y número permanente de los pilotos
    para cada temporada dentro de un rango de años, utilizando la API
    y caché local para reducir llamadas.

    Args:
        - start_year (int): año inicial del rango a consultar.
        - end_year (int): año final del rango a consultar.

    Returns:
        - mapping_drivers (dict): diccionario con estructura
          {year: {driverId: permanentNumber}} para cada temporada.
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
                    print("Exceso de requests, error 429")
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
    Genera y guarda un CSV por carrera con estadísticas agregadas de pit stops,
    incluyendo número de paradas y mediana de duración por piloto.

    Args:
        - pitstops (list[dict]): lista de registros de pit stops (uno por parada) obtenidos de la API.
        - mapping_drivers (dict): diccionario {year: {driverId: permanentNumber}} para asignar DriverNumber.
        - base_dir (str): directorio base donde se guardarán los CSV generados.
    """
    df = pd.DataFrame(pitstops)

    # duration a numérico
    df["duration"] = pd.to_numeric(df["duration"], errors="coerce")

    # añadir número de piloto
    df["DriverNumber"] = df.apply(lambda x: mapping_drivers.get(x["season"], {}).get(x["driverId"]), axis=1)

    df_agg = (df.groupby(["season", "round", "driverId", "DriverNumber"]).agg(
              NPitstops=("duration", "count"),
              MedianPitStopDuration=("duration", "median"))
            .reset_index()
            .rename(columns={"driverId": "DriverId"}))

    # escribir un CSV por carrera
    for (season, round), sub in df_agg.groupby(["season", "round"], sort=True):
        year_dir = os.path.join(base_dir, str(season))
        os.makedirs(year_dir, exist_ok=True)

        out_path = os.path.join(year_dir, f"round_{round}_API.csv")
        sub[["DriverId", "DriverNumber", "NPitstops", "MedianPitStopDuration"]].to_csv(out_path, index=False)



def build_merged_dataset(data_root="data", year_start=2019, year_end=2024, out_csv=None):
    """
    Construye un dataset combinado por temporada y carrera, uniendo los CSV del scraping
    (datos web) con los CSV generados desde la API (pit stops), y opcionalmente lo guarda.

    Args:
        - data_root (str): directorio raíz donde están las carpetas por año con los CSV.
        - year_start (int): primer año (incluido) a procesar.
        - year_end (int): último año (incluido) a procesar.
        - out_csv (str, optional): ruta de salida si se quiere guardar el dataset final en CSV.

    Returns:
        - big_df (DataFrame): dataframe final con todas las temporadas y carreras mergeadas.
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




