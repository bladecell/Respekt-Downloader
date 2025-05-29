import os
import subprocess
import tempfile
import sys
import chardet
from dataclasses import dataclass
from tamga import Tamga

@dataclass
class PodcastData:

    folder_path: str
    pls_file: str
    output_path: str
    book_title: str
    artist: str
    album: str
    date: str
    cover_image: str
    description: str

    def __init__(self, folder_path, pls_file, output_path=None, book_title=None, artist=None, album=None, date=None, cover_image=None, description=None):
        self.folder_path = folder_path
        self.pls_file = pls_file
        self.output_path = output_path
        self.book_title = book_title
        self.artist = artist
        self.album = album
        self.date = date
        self.cover_image = cover_image
        self.description = description

class CreatePodcast:
    def __init__(self, pd: PodcastData, logger: Tamga =None):
        self.logger = logger or Tamga(logToFile=False, logToJSON=False, logToConsole=True)
        self.pd = pd

    def __detect_encoding(self, file_path):
        with open(file_path, 'rb') as f:
            raw_data = f.read()
        result = chardet.detect(raw_data)
        return result['encoding']

    def __parse_pls(self):
        self.chapters = []
                
        pls_encoding = self.__detect_encoding(self.pd.pls_file)
        
        try:
            with open(self.pd.pls_file, 'r', encoding=pls_encoding) as f: 
                lines = f.readlines()
        except Exception as e:
            self.logger.error(f"Could not read PLS file {self.pd.pls_file}: {e}")
            return None
        
        
        num_entries_line = next((line for line in lines if line.startswith('NumberOfEntries=')), None)
        if not num_entries_line:
            self.logger.error("Invalid PLS file format - missing NumberOfEntries")
            return None
        
        num_entries = int(num_entries_line.split('=')[1].strip())
        
        
        for i in range(1, num_entries + 1):
            file_prefix = f"File{i}="
            title_prefix = f"Title{i}="
            length_prefix = f"Length{i}="
            
            file_line = next((line for line in lines if line.startswith(file_prefix)), None)
            title_line = next((line for line in lines if line.startswith(title_prefix)), None)
            length_line = next((line for line in lines if line.startswith(length_prefix)), None)
            
            if not file_line:
                self.logger.warning(f"Missing File{i} entry in PLS")
                continue
                
            filename = file_line[len(file_prefix):].strip()
            
            
            if title_line:
                title = title_line[len(title_prefix):].strip()
            else:
                title = os.path.splitext(filename)[0]
            
            
            length = 0
            if length_line:
                try:
                    length = int(length_line[len(length_prefix):].strip()) / 1000
                except ValueError:
                    self.logger.warning(f"Invalid length format for {filename}")
            
            self.chapters.append({
                'filename': filename,
                'title': title,
                'length': length
            })

    def __check_dependencies(self):
        """Check if FFmpeg is installed"""
        try:
            subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            self.logger.error("FFmpeg is not installed or not in PATH")
            sys.exit(1)

    def make(self):
        """
        Merge multiple audiobook MP3 files into one, preserving chapter markers
        based on a PLS playlist file.  Handles more metadata and cover art.
        """
        self.__check_dependencies()
        self.logger.info("Starting audiobook creation process...")

        self.pd.folder_path = os.path.abspath(self.pd.folder_path)
        if not os.path.exists(self.pd.folder_path) or not os.path.isdir(self.pd.folder_path):
            self.logger.error(f"Folder path does not exist: {self.pd.folder_path}")
            return False
        
        if not os.path.exists(self.pd.pls_file):
            self.logger.error(f"PLS file not found: {self.pd.pls_file}")
            return False
        
        if self.pd.output_path is None:
            folder_name = os.path.basename(self.pd.folder_path.rstrip('/\\'))
            self.pd.output_path = os.path.join(os.path.dirname(self.pd.folder_path), f"{folder_name}_merged.mp3")
        
        self.__parse_pls()
        if not self.chapters:
            self.logger.error("Could not parse chapters from PLS file")
            return False
        
        self.logger.success(f"Found {len(self.chapters)} chapters in PLS file")
        
        with tempfile.TemporaryDirectory() as temp_dir:

            concat_file = os.path.join(temp_dir, "concat.txt")
            with open(concat_file, 'w', encoding='utf-8') as f:
                f.write("")  
                
            chapters_file = os.path.join(temp_dir, "chapters.txt")
            with open(chapters_file, 'w', encoding='utf-8') as f:
                f.write(";FFMETADATA1\n\n")
                

                if self.pd.book_title:
                    f.write(f"title={self.pd.book_title}\n")
                if self.pd.artist:
                    f.write(f"artist={self.pd.artist}\n")
                if self.pd.album:
                    f.write(f"album={self.pd.album}\n")
                if self.pd.date:
                    f.write(f"date={self.pd.date}\n")
                if self.pd.description:
                    f.write(f"comment={self.pd.description}\n")
                
                if any([self.pd.book_title, self.pd.artist, self.pd.album, self.pd.date, self.pd.description]):
                    f.write("\n")
            
            found_chapters = 0
            current_time_ms = 0
            
            for idx, chapter in enumerate(self.chapters):
                self.logger.info(f"Processing chapter {idx+1}: {chapter['title']}")
                
                file_path = os.path.join(self.pd.folder_path, chapter['filename'])
                if not os.path.exists(file_path):
                    self.logger.warning(f"File not found: {file_path}")
                    continue
                
                with open(concat_file, 'a', encoding='utf-8') as f:
                    f.write(f"file '{file_path}'\n")
                
                duration_ms = chapter['length'] * 1000 if chapter['length'] > 0 else 0
                
                if duration_ms == 0:
                    try:
                        result = subprocess.run([
                            'ffprobe',
                            '-v', 'error',
                            '-show_entries', 'format=duration',
                            '-of', 'default=noprint_wrappers=1:nokey=1',
                            file_path
                        ], capture_output=True, text=True)
                        if result.returncode != 0:
                            self.logger.info(f"FFprobe error for {chapter['filename']}: {result.stderr.decode('utf-8', 'ignore')}")
                            duration_ms = 0
                        else:
                            duration_sec = float(result.stdout.strip())
                            duration_ms = int(duration_sec * 1000)
                    except (subprocess.SubprocessError, ValueError) as e:
                        self.logger.warning(f"Could not determine duration for {chapter['filename']}: {e}")
                        duration_ms = 0
                
                start_ms = current_time_ms
                end_ms = start_ms + duration_ms if duration_ms > 0 else 0
                
                with open(chapters_file, 'a', encoding='utf-8') as f:
                    f.write("[CHAPTER]\n")
                    f.write("TIMEBASE=1/1000\n")
                    f.write(f"START={start_ms}\n")
                    
                    if end_ms > start_ms:
                        f.write(f"END={end_ms}\n")
                        current_time_ms = end_ms
                    
                    f.write(f"title={chapter['title']}\n\n")
                
                found_chapters += 1
            
            if found_chapters == 0:
                self.logger.error("No valid chapter files found")
                return False
            
            temp_output = os.path.join(temp_dir, "temp_merged.mp3")
            
            self.logger.info(f"Merging {found_chapters} audio files...")
            
            try:
                result = subprocess.run([
                    'ffmpeg',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', concat_file,
                    '-c', 'copy',
                    temp_output
                ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode != 0:
                    print(f"FFmpeg error during concatenation: {result.stderr.decode('utf-8', 'ignore')}")
                    return False
            except subprocess.CalledProcessError as e:
                print(f"Error during FFmpeg concatenation: {e}")
                print(f"FFmpeg stderr: {e.stderr.decode('utf-8', 'ignore')}")
                return False
            
            self.logger.info("Adding chapter metadata...")
            
            ffmpeg_args = [
                'ffmpeg',
                '-i', temp_output,
                '-i', chapters_file,
                '-map_metadata', '1',
                '-codec', 'copy',
            ]

            if self.pd.cover_image:
                if not os.path.exists(self.pd.cover_image):
                    self.logger.warning(f"Cover image not found: {self.pd.cover_image}")
                else:
                    ffmpeg_args = [
                        'ffmpeg',
                        '-i', temp_output,       
                        '-i', chapters_file,     
                        '-i', self.pd.cover_image,       
                        '-map', '0',             
                        '-map_metadata', '1',    
                        '-map', '2',             
                        '-c', 'copy',
                        '-id3v2_version', '3',
                        '-metadata:s:v', 'title=Cover',
                        '-metadata:s:v', 'comment=Cover (front)',
                    ]
            metadata_args = []
            if self.pd.book_title:
                metadata_args.extend(['-metadata', f'title={self.pd.book_title}'])
            if self.pd.artist:
                metadata_args.extend(['-metadata', f'artist={self.pd.artist}'])
            if self.pd.album:
                metadata_args.extend(['-metadata', f'album={self.pd.album}'])
            if self.pd.date:
                metadata_args.extend(['-metadata', f'date={self.pd.date}'])
            if self.pd.description:
                metadata_args.extend(['-metadata', f'comment={self.pd.description}'])
            ffmpeg_args.extend(metadata_args)
            ffmpeg_args.append(self.pd.output_path)
            
            try:
                result = subprocess.run(ffmpeg_args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode != 0:
                    self.logger.error(f"FFmpeg error adding metadata: {result.stderr.decode('utf-8', 'ignore')}")
                    return False
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Adding chapter metadata: {e}")
                self.logger.error(f"FFmpeg stderr: {e.stderr.decode('utf-8', 'ignore')}")
                return False
        
        self.logger.success(f"Successfully created audiobook with {found_chapters} chapters: {self.pd.output_path}")
        return True

if __name__ == "__main__":
    
    folder = r"V:\Data\mp3\app\respekt"
    pls_file = os.path.join(folder, "playlist.pls")
    output = 'Respekt_21_2025.mp3'
    title = "Respekt 21/2025"
    artist = "Respekt"
    album = None
    date = 2025
    cover = os.path.join(folder, "cover.jpg") 
    description = 'Respekt 21/2025 - Audiobook'
    
    pd = PodcastData(
        folder,
        pls_file,
        output,
        title,
        artist,
        album,
        date,
        cover,
        description
    )

    cp = CreatePodcast(pd)
    cp.make()
