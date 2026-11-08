# Import the required libraries.
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import scrapy

class Racelink:
    '''
    Structure that carries the 'Round', the GP name and the URL of the Report found
    '''
    def __init__(self, n_round: int, grand_prix: str, report_url: str):
        self.n_round = n_round
        self.grand_prix = grand_prix
        self.report_url = report_url
    def __str__(self) -> str:
        return f'RaceLink(n_round={self.n_round}, grand_prix={self.grand_prix}, report_url={self.report_url})'

class F1WikiSpider(scrapy.Spider):
    '''
    Spider that:
    - Visits the page of each requested year, e.g. 2021_Formula_One_World_Championship.
    - Finds the 'Grand Prix' table and extracts the 'Report' links from it.
    - Visits each of those links, extracts the 'Race classification' table and saves it as a csv in data/<year>/.
    '''

    name = 'f1_wiki'

    # Force a specific configuration for this spider.
    custom_settings = {'ROBOTSTXT_OBEY': True, 'DOWNLOAD_DELAY': 1.0}

    def __init__(self, start_year: str = '2019', end_year: str = 2026, *args, **kwargs):
        '''
        start_year (str): year where the search starts, 2019 by default.
        end_year (str): year where the search ends, 2026 by default.
        '''
        # Initialise the base class and pass args/kwargs so that Scrapy configures the spider correctly.
        super().__init__(*args, **kwargs)

        self.start_year = int(start_year)
        self.end_year = int(end_year)
        self.out_path = Path('data')    # Output directory.
        # Build the URLs.
        self.start_urls = [f"https://en.wikipedia.org/wiki/{year}_Formula_One_World_Championship" for year in range(self.start_year, self.end_year + 1)]

    def slugify(self, text: str) -> str:
        '''
        Turns a name into something safe to use as a file name (removes odd characters, replaces spaces with underscores)

        Args:
            text (str): name to clean.
        '''
        text = text.strip()
        # Replace the spaces.
        text = re.sub(r'\s+', '_', text)
        # Remove every character that is not a letter, digit, _ or -.
        text = re.sub(r"[^A-Za-z0-9_\-]+", '', text)
        # Keep it short: return the first 120 characters.
        return text[:120] if len(text) > 120 else text

    def parse_year_from_url(self, url: str):
        '''
        Extracts the year from the URL passed as argument.
        '''
        m = re.search(r'/wiki/(\d{4})_Formula_One_World_Championship', url)
        return int(m.group(1)) if m else None

    def select_GP_table(self, response: scrapy.http.Response):
        '''
        Inspecting the page HTML shows that Wikipedia usually has:
        '### Grands Prix (id='Grands_Prix') followed by a table -> wikitable'. Knowing this, this function runs a query that extracts
        that table.
        '''
        table = response.xpath(
        '//*[@id="Grands_Prix"]/ancestor::div[contains(@class,"mw-heading")][1]'
        '/following-sibling::table[contains(@class,"wikitable")][1]'
    )

        # Fallback in case the div.mw-heading does not exist for some year
        if not table:
            table = response.xpath(
                '//*[@id="Grands_Prix"]/ancestor::*[self::h2 or self::h3 or self::h4][1]'
                '/following-sibling::table[contains(@class,"wikitable")][1]'
            )

        return table[0] if table else None

    def extract_report_url(self, table: scrapy.selector.Selector, response: scrapy.http.Response):
        '''
        Extracts the link of each 'Report' from every row of the given table.

        Args:
            table (scrapy.selector.Selector): grand prix table.
            response (scrapy.http.Response): HTTP response of the requested page, here: https://en.wikipedia.org/wiki/<year>_Formula_One_World_Championship
        '''
        out = []                            # List storing the RaceLink objects of each 'Report'.
        filas = table.xpath(".//tr[td]")    # HTML rows
        for fila in filas:                  # Extract the data we need from each row.

            # Extract the round (column 1).
            round = ''.join(fila.xpath("./th[1]//text()").getall()).strip()
            if not round.isdigit():         # It must be a number, otherwise skip to the next row.
                continue
            n_round = int(round)

            # Extract the GP name (column 2), making sure we always have a valid name.
            name_GP = (fila.xpath("./td[1]//a[last()]/text()").get() or '').strip() or f'Round{n_round}'

            # Extract the 'Report' link.
            report_href = fila.xpath('.//a[normalize-space()="Report"]/@href').get()
            if not report_href:             # If no link was found, skip to the next row.
                continue

            # Add the data to the list as a RaceLink object.
            out.append(Racelink(n_round, name_GP, response.urljoin(report_href)))
        return out

    def parse(self, response: scrapy.http.Response):
        '''
        Processes each initial response, extracts the 'Report' links and yields new requests to follow them.
        We locate the 'Grand Prix' table in the page, extract the 'Report' links and create a new Request for each report. That
        new link is handled by parse_report().

        Args:
            response (scrapy.http.Response): HTTP response of the requested page, here: https://en.wikipedia.org/wiki/<year>_Formula_One_World_Championship
        '''

        year = self.parse_year_from_url(response.url)
        if year is None:        # Something went wrong and the year could not be extracted, log a warning.
            self.logger.warning(f'Could not extract the year from the url {response.url}. ')
            return
        GP_table = self.select_GP_table(response)
        if GP_table is None:    # Something went wrong and the table could not be extracted, log a warning.
            self.logger.warning(f"Could not find the 'Grands Prix' table for the url {response.url}. ")
            return
        race_links = self.extract_report_url(GP_table, response)
        if not race_links:      # Something went wrong and no 'Report' links were found, log a warning.
            self.logger.warning(f"No 'Report' links found for the url {response.url}. ")
            return

        for rl in race_links:
            # Queue a request to the 'Report' link and, when the response arrives, call parse_report with the data.
            yield response.follow(rl.report_url, callback=self.parse_report, cb_kwargs={'year': year, 'n_round': rl.n_round, 'grand_prix': rl.grand_prix},)

    def parse_report(self, response: scrapy.http.Response, year: int, n_round: int, grand_prix: str):
        '''
        Processes the given 'Report' page, locates the requested table (Race classification), turns it into a DataFrame and saves it
        as a csv in the corresponding folder.

        Args:
            response (scrapy.http.Response): HTTP response of the 'Report' page of the GP.
            year (int): season year of the GP.
            n_round (int): round number of the GP within the year.
            grand_prix (str): name of the GP.
        '''
        table_html = self.extract_RC_table_html(response)
        if table_html is None:
            return

        # Store the information in a csv.
        df = pd.read_html(table_html)[0]
        df.columns = [str(col).strip() for col in df.columns]

        pos_col = df.columns[0] # Take the name of the first column (Pos.)
        pos = df[pos_col].astype(str).str.strip() # Take that column and make sure everything is a str.

        # Mask to filter the rows
        pattern = re.compile(r'^(?:\d+|Ret|DNS|DNF|DSQ|NC|EX)')

        df = df[pos.str.match(pattern, na=False)].copy()


        year_dir = self.out_path / str((year))
        year_dir.mkdir(parents=True, exist_ok=True)     # Create the directory if it does not exist yet.

        filename = f'{n_round:02d}_{self.slugify(grand_prix)}.csv'
        out_path = year_dir / filename

        # Save the DataFrame data to a csv file.
        df.to_csv(out_path, index=False, encoding='utf-8')

        # Report that the download has finished.
        self.logger.info(f"Saved the data for this url to {out_path}. ")

    def extract_RC_table_html(self, response: scrapy.http.Response):
        '''
        Locates and returns the HTML of the race result table within a 'Report' page (the first table).
        If it does not exist, logs a warning and returns None.

        Args:
            response (scrapy.http.Response): HTTP response of the 'Report' page of the GP.
        '''
        table = response.xpath(
        '//*[@id="Race_classification"]/ancestor::div[contains(@class,"mw-heading")][1]'
        '/following-sibling::table[contains(@class,"wikitable")][1]'
    )

        # Fallback in case there is no div.mw-heading
        if not table:
            table = response.xpath(
                '//*[@id="Race_classification"]/ancestor::*[self::h2 or self::h3 or self::h4][1]'
                '/following-sibling::table[contains(@class,"wikitable")][1]'
            )

        if not table:
            self.logger.warning(
                "No table found under 'Race classification' in %s",
                response.url,
            )
            return None

        return table.get()