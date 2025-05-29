import requests
import os
from urllib.parse import urlparse
from tamga import Tamga
import zipfile
import json
from create_podcast import PodcastData
from bs4 import BeautifulSoup
from datetime import datetime
import re

class AudiotekaBook:

    id: str
    slug: str
    name: str
    image_url: str
    kind: str
    description: str
    created_at: datetime
    author: str
    album: str

    def __init__(self, slug: str, download_dir:str = None, logger=None):
        self.logger = logger or Tamga(logToFile=False, logToJSON=False, logToConsole=True)
        self.download_dir = download_dir
        self.extracted_dir = None
        self.cover_path = None
        self.__parse_product(slug)

    def __parse_product(self, slug: str):

        url = f'https://audioteka.com/cz/audiokniha/{slug}/'

        allowed_keys = {'id', 'slug', 'name', 'image_url', 'kind', 'description'}
        r = requests.get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        script_tag = soup.find('script', {'id': '__NEXT_DATA__'})
        if script_tag:
            json_data = script_tag.string
            data = json.loads(json_data)
            for key, value in data['props']['pageProps']['audiobook'].items():
                if key in allowed_keys:
                    setattr(self, key, value)
            self.created_at = datetime.fromisoformat(data['props']['pageProps']['audiobook']['created_at'])
            setattr(self, 'author', data['props']['pageProps']['audiobook']['_embedded']['app:author'][0]['name'])
            setattr(self, 'album', data['props']['pageProps']['audiobook']['_embedded']['app:contained-in'][0]['name'])
        else:
            self.logger.error("No script tag found in the HTML")
            return None


    def __download_cover(self):
        if not self.image_url:
            self.logger.error("No image URL found")
            return None
        try:
            response = requests.get(self.image_url)
            response.raise_for_status()
            self.cover_path = os.path.join(self.extracted_dir, f"{self.__safe_name(self.name)}.jpg")
            with open(self.cover_path, 'wb') as f:
                f.write(response.content)
            self.logger.success(f"Cover downloaded to: {self.cover_path}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to download cover: {e}")
            return None
        
    def __safe_name(self, str):
        return re.sub(r'[^\w\-]', '_', str)

    def download_file(self, session: requests.Session):
        url = f"https://audioteka.com/cz/v2/me/audiobooks/{self.id}/download"
        if not self.download_dir:
            self.logger.error("Download directory not set")
            return None
        if not os.path.isdir(self.download_dir): os.mkdir(self.download_dir)
        self.downloaded_file_path = os.path.join(self.download_dir, self.__safe_name(self.name) + ".zip")
        
        self.logger.info(f"Downloading: {url} to {self.downloaded_file_path}")
        try:
            result = urlparse(url)
            if not all([result.scheme, result.netloc]):
                raise ValueError("Invalid URL")
        except Exception as e:
            self.logger.error(f"Invalid URL: {e}")
            return None

        os.makedirs(self.download_dir, exist_ok=True)

        try:
            with session.get(url, stream=True) as response:
                response.raise_for_status()
                with open(self.downloaded_file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024):
                        f.write(chunk)
                self.logger.success(f"Downloaded to: {self.downloaded_file_path}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Download failed: {e}")
            if os.path.exists(self.downloaded_file_path):
                os.remove(self.downloaded_file_path)
            return None
        
    def extract_zip(self):
        if not os.path.exists(self.downloaded_file_path):
            self.logger.error(f"File does not exist: {self.downloaded_file_path}")
            return None
        self.extracted_dir = os.path.join(self.download_dir, self.name)
        os.makedirs(self.extracted_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(self.downloaded_file_path, 'r') as zip_ref:
                zip_ref.extractall(self.extracted_dir)
                self.logger.success(f"Extracted to: {self.extracted_dir}")
        except zipfile.BadZipFile as e:
            self.logger.error(f"Bad zip file: {e}")
            return None
        
    def create_podcast_data(self):
        return PodcastData(
            self.extracted_dir,
            os.path.join(self.extracted_dir, 'playlist.pls'),
            os.path.join(self.download_dir, self.__safe_name(self.slug) + '.mp3'),
            self.name,
            self.author,
            self.album,
            self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            self.__download_cover(),
            self.description,
        )

    