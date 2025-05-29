import asyncio
from tamga import Tamga
from cookie_manager import get_cookies
from create_podcast import CreatePodcast
from audioteka_book import AudiotekaBook
import requests
from bs4 import BeautifulSoup
import json
import shutil
import os

logger = Tamga(
        logToFile=True,
        logToJSON=True,
        logToConsole=True
    )

refreshurl = f'https://audioteka.com/cz/katalog/respekt/'

password = os.getenv('password')
email = os.getenv('email')
respekt_folder = os.getenv('respekt_folder')
download_directory = os.getenv('download_directory')


def parse_version(name):
    normalized = name.lower().replace('_', '-')
    parts = normalized.split('-')
    
    week = int(parts[-2])
    year = int(parts[-1])
    return (year, week)

def main():

    if not all([password, email, respekt_folder, refreshurl, download_directory]):
        raise logger.error("Missing required environment variables")
        return
    r = requests.get(refreshurl)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    script_tag = soup.find('script', {'id': '__NEXT_DATA__'})
    slugs = []
    if script_tag:
        json_data = script_tag.string
        data = json.loads(json_data)
        for product in data['props']['pageProps']['productList']['_embedded']['app:product']:
            slugs.append(product['slug'])

    respekt_files = [file.strip('.mp3') for file in os.listdir(respekt_folder) if file.endswith('.mp3')]

    latest_file = max(respekt_files, key=lambda x: parse_version(x))
    latest_year, latest_week = parse_version(latest_file)

    newer_slugs = []
    for slug in slugs:
        year, week = parse_version(slug)
        if (year > latest_year) or (year == latest_year and week > latest_week):
            newer_slugs.append(slug)

    logger.info(f"Latest local file: {latest_file}")

    if not newer_slugs:
        logger.info("No new releases available")
        return

    logger.info(f"Newer releases available: {newer_slugs}")

    try:
        cookies = asyncio.run(get_cookies(email, password))
    except Exception as e:
        logger.error(f"Failed to get cookies: {e}")
        
    session = requests.Session()
    for cookie in cookies:
        session.cookies.set_cookie(cookie)

    params = {
        'page': '1',
        'limit': '30',
    }

    for new_slug in newer_slugs:
        download_directory_slug = os.path.join(download_directory, new_slug)
        ab = AudiotekaBook(new_slug, download_directory_slug, logger)

        logger.info(f"Book name: {ab.name}")

        ab.download_file(session)
        ab.extract_zip()
        cp = CreatePodcast(ab.create_podcast_data())
        cp.make()
        logger.info(f"Copying podcast to: {respekt_folder}")
        shutil.copy(cp.pd.output_path, respekt_folder)
        logger.success(f"Podcast {ab.name} created successfully")

        shutil.rmtree(download_directory_slug, ignore_errors=True)
    logger.success("All podcasts processed successfully")

    
        

if __name__ == '__main__':
    main()