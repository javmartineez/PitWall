# Importamos las librerías necesarias. 
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import scrapy

class Racelink: 
    '''
    Estructura con la que transportamos el 'Round', nombre del GP y URL del Report encontrados
    '''
    def __init__(self, n_round: int, grand_prix: str, report_url: str):
        self.n_round = n_round
        self.grand_prix = grand_prix
        self.report_url = report_url
    def __str__(self) -> str: 
        return f'RaceLink(n_round={self.n_round}, grand_prix={self.grand_prix}, report_url={self.report_url})'

class F1WikiSpider(scrapy.Spider): 
    '''
    Creamos un spider que: 
    - Visita la web para cada año solicitado: ej: 2021_Formula_One_World_Championship. 
    - Encuentra la tabla 'Grand Prix' y de ella extrae los enlaces 'Report'. 
    - Visita cada uno de estos enlaces y extrae la tabla 'Race classification' y la guarda como csv dentro de data/<anio>/. 
    '''

    name = 'f1_wiki'

    # Forzamos una configuración específica para el spider. 
    custom_settings = {'ROBOTSTXT_OBEY': True, 'DOWNLOAD_DELAY': 1.0}

    def __init__(self, start_year: str = '2019', end_year: str = 2026, *args, **kwargs): 
        '''
        start_year (str): el año por el que empezamos la búsqueda, 2019 por defecto. 
        end_year (str): el año en el que finalizamos la búsqueda, 2026 por defecto. 
        '''
        # Inicializamos la clase base y pasamos los argumentos args/kwargs para que Scrapy configure el spider correctamente. 
        super().__init__(*args, **kwargs)

        self.start_year = int(start_year)
        self.end_year = int(end_year)
        self.out_path = Path('data')    # Directorio de salida. 
        # Generamos las urls. 
        self.start_urls = [f"https://en.wikipedia.org/wiki/{year}_Formula_One_World_Championship" for year in range(self.start_year, self.end_year + 1)]

    def slugify(self, text: str) -> str: 
        '''
        Función que convierte un nombre en algo que no cause problemas como nombre de un fichero (quita caracteres raros, sustituye espacios por guiones bajos)
        
        Args: 
            text (str): nombre para limpiar. 
        '''
        text = text.strip()
        # Sustituimos los espacios. 
        text = re.sub(r'\s+', '_', text)
        # Eliminamos todo caracter que no sea leatra, número, _ o -. 
        text = re.sub(r"[^A-Za-z0-9_\-]+", '', text)
        # Para que no sea muy largo devolvemos los primeros 120 caracteres. 
        return text[:120] if len(text) > 120 else text 

    def parse_year_from_url(self, url: str): 
        '''
        Función que extrae el correspondiente a la url recibida por argumentos. 
        '''
        m = re.search(r'/wiki/(\d{4})_Formula_One_World_Championship', url)
        return int(m.group(1)) if m else None
    
    def select_GP_table(self, response: scrapy.http.Response):
        '''
        Habiendo consultado el HTML correspondiente a la web vemos que wikipedia suele tener: 
        '### Grands Prix (id='Grands_Prix') seguido por una tabla -> wikitable'. Sabiendo esto, esta función realiza un request que extrae 
        la información correspondiente a esta tabla. 
        '''
        table = response.xpath(
        '//*[@id="Grands_Prix"]/ancestor::div[contains(@class,"mw-heading")][1]'
        '/following-sibling::table[contains(@class,"wikitable")][1]'
    )

        # Fallback por si en algún año no existe el div.mw-heading
        if not table:
            table = response.xpath(
                '//*[@id="Grands_Prix"]/ancestor::*[self::h2 or self::h3 or self::h4][1]'
                '/following-sibling::table[contains(@class,"wikitable")][1]'
            )

        return table[0] if table else None
    
    def extract_report_url(self, table: scrapy.selector.Selector, response: scrapy.http.Response): 
        '''
        Función que extrae los links asociados a cada 'Report' de cada fila de la tabla recibida por argumentos. 

        Args: 
            table (scrapy.selector.Selector): tabla grand prix. 
            response (scrapy.http.Response): respuesta http de la página buscada, en este caso: https://en.wikipedia.org/wiki/<anio>_Formula_One_World_Championship 
        '''
        out = []                            # Lista para almacenar los objetos RaceLink asociados a cada 'Report'. 
        filas = table.xpath(".//tr[td]")    # filas del HTML
        for fila in filas:                  # En cada fila extraemos los datos que buscamos. 
            
            # Extramos el round (columna 1). 
            round = ''.join(fila.xpath("./th[1]//text()").getall()).strip()
            if not round.isdigit():         # Debe ser un número, sino pasamos a la siguiente fila. 
                continue
            n_round = int(round)
            
            # Extraemos el nombre del GP (columna 2), nos aseguramos de siempre tener un nombre válido. 
            name_GP = (fila.xpath("./td[1]//a[last()]/text()").get() or '').strip() or f'Round{n_round}'
                
            # Extraemos el link asociado al 'Report'. 
            report_href = fila.xpath('.//a[normalize-space()="Report"]/@href').get()
            if not report_href:             # Si no se ha encontrado un link pasamos a la siguiente fila. 
                continue

            # Añadimos los datos a la lista como objeto RaceLink. 
            out.append(Racelink(n_round, name_GP, response.urljoin(report_href)))
        return out

    def parse(self, response: scrapy.http.Response): 
        '''
        Función que procesa cada respuesta inicial, extrae los enlaces de 'Report' y produce nuevas requests para seguir estos. 
        Localizamos la tabla de 'Grand Prix' en la url, extraemos los enlaces 'Report' y hacemos ceamos una nueva Request a cada report. Para trabajar con este 
        nuevo enlace llamamos a la función parse_report(). 
        
        Args: 
            response (scrapy.http.Response): respuesta http de la página buscada, en este caso: https://en.wikipedia.org/wiki/<anio>_Formula_One_World_Championship
        '''

        year = self.parse_year_from_url(response.url)
        if year is None:        # Se ha producido un error y no se ha podido extraer el año, mandamos un warning. 
            self.logger.warning(f'No se pudo extraer el año correspondiente a la url {response.url}. ')
            return 
        GP_table = self.select_GP_table(response)
        if GP_table is None:    # Se ha producido un error y no se ha podido extraer la tabla, mandamos un warning. 
            self.logger.warning(f"No se encontró la tabla de 'Grands Prix' asociada a la url {response.url}. ")
            return
        race_links = self.extract_report_url(GP_table, response)
        if not race_links:      # Se ha producido un error y no se han podido encontrar los enlaces asociados a los 'Report', mandamos un warning. 
            self.logger.warning(f"No se encontraron enlaces 'Report' asociados a la url {response.url}. ")
            return
        
        for rl in race_links: 
            # Encolamos una request al enlace 'Report' y, cuando obtengamos la respuesta, llamamos a parse_report pasandole los datos. 
            yield response.follow(rl.report_url, callback=self.parse_report, cb_kwargs={'year': year, 'n_round': rl.n_round, 'grand_prix': rl.grand_prix},)
    
    def parse_report(self, response: scrapy.http.Response, year: int, n_round: int, grand_prix: str): 
        '''
        Función que procesa la página de 'Report' recibida por argumentos y localiza la tabla pedida (Race classification), la convierte en un DataFrame y la guarda 
        en formato csv en su carpeta correspondiente. 

        Args: 
            response (scrapy.http.Response): Resuesta HTTP de la página 'Report' del GP asociado. 
            year (int): Año de la temporada asociado al GP. 
            n_round (int): número de ronda del GP del año. 
            grand_prix (str): Nombre del GP. 
        '''
        table_html = self.extract_RC_table_html(response)
        if table_html is None: 
            return 
        
        # Almacenamos la información en un csv. 
        df = pd.read_html(table_html)[0]
        df.columns = [str(col).strip() for col in df.columns]
        
        pos_col = df.columns[0] # Coge el nombre de la primera columna (Pos.)
        pos = df[pos_col].astype(str).str.strip() # Coge esa columna y asegura que toda sea en formato str.

        # Máscara para filtrar las filas
        pattern = re.compile(r'^(?:\d+|Ret|DNS|DNF|DSQ|NC|EX)')

        df = df[pos.str.match(pattern, na=False)].copy()

        
        year_dir = self.out_path / str((year))
        year_dir.mkdir(parents=True, exist_ok=True)     # Creamos el directorio asociado si no está creado, si no está controlamos en error. 

        filename = f'{n_round:02d}_{self.slugify(grand_prix)}.csv'
        out_path = year_dir / filename

        # Almacenamos los datos del DataFrame en un fichero csv. 
        df.to_csv(out_path, index=False, encoding='utf-8')

        # Avisamos de que ha terminado la descarga. 
        self.logger.info(f"Se han guardado los datos asociados a la url en {out_path}. ")

    def extract_RC_table_html(self, response: scrapy.http.Response): 
        '''
        Función que localiza y devuelve el HTML asociado a la tabla de resultado de carrera dentro de una página de 'Report' y devuelve la primera tabla. 
        Si esta no existe, registra un warning y devuelve None.

        Args: 
            response (scrapy.http.Response): Respuesta HTTP de la página 'Report' del GP. 
        '''
        table = response.xpath(
        '//*[@id="Race_classification"]/ancestor::div[contains(@class,"mw-heading")][1]'
        '/following-sibling::table[contains(@class,"wikitable")][1]'
    )

        # Fallback por si no hay div.mw-heading
        if not table:
            table = response.xpath(
                '//*[@id="Race_classification"]/ancestor::*[self::h2 or self::h3 or self::h4][1]'
                '/following-sibling::table[contains(@class,"wikitable")][1]'
            )

        if not table:
            self.logger.warning(
                "No se encontró ninguna tabla bajo 'Race classification' en %s",
                response.url,
            )
            return None

        return table.get()