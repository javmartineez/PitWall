from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from apartado_scrapy.spiders.f1_results import F1WikiSpider
import jolpicaF1_api as api


def apartado_scrapy(start_year: int, end_year: int):
    """
    Runs the F1 data scraping process for a range of years
    by launching the corresponding Scrapy spider.

    Args:
        - start_year (int): first year of the range to scrape.
        - end_year (int): last year of the range to scrape.
    """
    settings = get_project_settings()
    process = CrawlerProcess(settings)

    # Pass the parameters to the spider. 
    process.crawl(F1WikiSpider, start_year=start_year, end_year=end_year)
    process.start()



def apartado_api(start_year, end_year):
    """
    Fetches and processes F1 API data for a range of years,
    generating intermediate CSV files and a final combined dataset.

    Args:
        - start_year (int): first year of the range to query from the API.
        - end_year (int): last year of the range to query from the API.

    Returns:
        - complete_df (DataFrame): final dataset with all the combined information.
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