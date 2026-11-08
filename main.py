from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from apartado_scrapy.spiders.f1_results import F1WikiSpider
import jolpicaF1_api as api


def apartado_scrapy(start_year: int, end_year: int):
    """
    Ejecuta el proceso de scraping de datos de F1 para un rango de años,
    lanzando el spider correspondiente con Scrapy.

    Args:
        - start_year (int): año inicial del rango a scrapear.
        - end_year (int): año final del rango a scrapear.
    """
    settings = get_project_settings()
    process = CrawlerProcess(settings)

    # Pasamos los parámetros al spider creado. 
    process.crawl(F1WikiSpider, start_year=start_year, end_year=end_year)
    process.start()



def apartado_api(start_year, end_year):
    """
    Obtiene y procesa datos de la API de F1 para un rango de años,
    generando ficheros CSV intermedios y un dataset final combinado.

    Args:
        - start_year (int): año inicial del rango a consultar en la API.
        - end_year (int): año final del rango a consultar en la API.

    Returns:
        - complete_df (DataFrame): dataset final con toda la información combinada.
    """
    pitstops = api.all_pitstops_in(start_year, end_year)
    driver_numbers = api.driverid_to_number(start_year, end_year)

    api.write_pitstops_csvs(pitstops, driver_numbers)
    
    complete_df = api.build_merged_dataset(out_csv="Merged_data.csv")

    return complete_df



if __name__ == '__main__': 
    start_year = 2019 
    end_year = 2024 
    apartado_scrapy(start_year, end_year)
    complete_df = apartado_api(start_year, end_year)