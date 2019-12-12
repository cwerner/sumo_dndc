# parser.py

import io
import pandas as pd

from enum import Enum, auto

import xml.etree.ElementTree as ET
import xml.dom.minidom as MD

from pathlib import Path
from typing import Union, Optional, Any

__all__ = ['Parser', 'InFile', 'OutFile']

PathOrStr = Union[Path,str]

DEBUG = False

class InFile(Enum):
    """valid DNDC input file types"""
    AIRCHEM = auto()
    CLIMATE = auto()
    EVENTS = auto()
    SITE = auto()
    SETUP = auto()

class OutFile(Enum):
    """valid DNDC output file types"""

    # currently only soilchemistry daily allowed
    SOILCHEM_DAILY = auto()

class BaseParser:
    _fileName = None

    @classmethod
    def is_parser_for(cls, fileType: InFile) -> bool:
        return fileType == cls._fileType

    def __init__(self, fileType: InFile) -> None:
        self._data = None
        self._name = None
        self._path = None
        self._type = None

        if isinstance(fileType, InFile):
            self._type = fileType
        else:
            print('Not a valid input type')


    def __repr__(self):
        return f'Parser: {self._type}, {self._path}\nData excerpt:\n{"" if self._data is None else repr(self._data.head())}'

    def parse(self, inFile: Path):
        """parse source dndc file"""
        raise NotImplementedError

    def encode(self):
        """convert data to embedding vector"""
        raise NotImplementedError


class XmlParser(BaseParser):
    def __init__(self, fileType: InFile) -> None:
        super().__init__(fileType)

    def __repr__(self):
        # pretty print xml
        pretty_xml = MD.parseString(ET.tostring(self._data)).toprettyxml(encoding='utf8').decode()
        # strip whitespace lines
        pretty_xml = '\n'.join([line for line in pretty_xml.split('\n') if line.strip() != ""][:6])
        return f'Parser: {self._type}, {self._path}\nData excerpt:\n{"" if self._data is None else pretty_xml}'


class TxtParser(BaseParser):
    def __init__(self, fileType: InFile, inFile: Optional[PathOrStr] = None) -> None:
        super().__init__(fileType)

        if inFile:
            self._path = Path(inFile)
            self._name = self._path.name
            self._parse(self._path)

    def _parse(self, inFile: PathOrStr, skip_header: bool = False):
        print("Parsing TxtFile", inFile)
        fileInMem = io.StringIO(Path(inFile).read_text())

        if skip_header:
            for line in fileInMem:
                if "%data" in line:
                    break

        data = pd.read_csv(fileInMem, delim_whitespace=True)
        self._data = data
        self._path = Path(inFile)
        self._name = Path(inFile).name



class AirchemParser(TxtParser):
    _fileType = InFile.AIRCHEM

    def __init__(self, inFile: Optional[PathOrStr] = None) -> None:
        super().__init__(self._fileType)
        if inFile:
            self.parse(inFile)
    
    def parse(self, inFile: PathOrStr) -> None:
        if inFile:
            self._parse(inFile, skip_header=True)
        else:
            print('you need to provide a file to parse')


class ClimateParser(TxtParser):
    _fileType = InFile.CLIMATE
   
    def __init__(self, inFile: Optional[PathOrStr] = None) -> None:
        super().__init__(self._fileType)
        if inFile:
            self.parse(inFile)
    
    def parse(self, inFile: PathOrStr) -> None:
        if inFile:
            self._parse(inFile, skip_header=True)
        else:
            print('you need to provide a file to parse')


class SiteParser(XmlParser):
    _fileType = InFile.SITE

    def __init__(self, inFile: Optional[PathOrStr] = None) -> None:
        super().__init__(self._fileType)
        if inFile:
            self.parse(inFile)

    def _parse(self, inFile: PathOrStr, id: Optional[str] = None) -> None:
        root = ET.parse(Path(inFile)).getroot()

        sites = root.findall('./site')
          
        if id:
            for site in sites:
                if site.id == id:
                    break
        else:
            site = sites[0]

        self._data = site.find('./soil')
        self._path = Path(inFile)
        self._name = Path(inFile).name

    def parse(self, inFile: PathOrStr, id: Optional[str] = None) -> None:
        self._parse(inFile, id=id)


# factory
class Parser:
    """a parser factory for a set of dndc file types"""
    # TODO: add an option to "sense" the file by parsing the optionally provided file name
    parsers = [AirchemParser, ClimateParser, SiteParser]
    def __new__(self, fileType: InFile, inFile: Optional[PathOrStr] = None) -> InFile:
        matched_parsers = [r for r in self.parsers if r.is_parser_for(fileType)]
        if len(matched_parsers) == 1:
            print(f'Creating Parser:{matched_parsers[0]}')
            return matched_parsers[0](inFile)
        elif len(matched_parsers) > 1:
            print('Multiple parsers matched. Something is very wrong here!')
        else:
            raise NotImplementedError