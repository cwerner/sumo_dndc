# parser.py

import io
import numpy as np
import pandas as pd

from enum import Enum, auto

import xml.etree.ElementTree as ET
import xml.dom.minidom as MD

from pathlib import Path
from typing import Union, Optional, Any, List

__all__ = ["Parser", "InFile", "OutFile"]

PathOrStr = Union[Path, str]

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
    DAILY = auto()
    YEARLY = auto()


class BaseParser:
    _fileName = None

    @classmethod
    def is_parser_for(cls, fileType: Union[InFile, OutFile]) -> bool:
        return fileType == cls._fileType

    def __init__(self, fileType: Union[InFile, OutFile]) -> None:
        self._data = None
        self._name = None
        self._path = None
        self._type = None

        if isinstance(fileType, InFile) or isinstance(fileType, OutFile):
            self._type = fileType
        else:
            print("Not a valid input type")

    def __repr__(self):
        return f'Parser: {self._type}, {self._path}\nData excerpt:\n{"" if self.data is None else repr(self.data.head())}'

    @property
    def data(self):
        return self._data

    def parse(self, inFile: Path):
        """parse source dndc file"""
        raise NotImplementedError

    def encode(self):
        """convert data to embedding vector"""
        raise NotImplementedError


class XmlParser(BaseParser):
    def __init__(self, fileType: Union[InFile, OutFile]) -> None:
        super().__init__(fileType)

    def __repr__(self):
        pretty_xml = (
            MD.parseString(ET.tostring(self.data)).toprettyxml(encoding="utf8").decode()
        )
        # strip whitespace lines
        pretty_xml = "\n".join(
            [line for line in pretty_xml.split("\n") if line.strip() != ""][:6]
        )
        return f'Parser: {self._type}, {self._path}\nData excerpt:\n{"" if self.data is None else pretty_xml}'


class TxtParser(BaseParser):
    def __init__(
        self, fileType: Union[InFile, OutFile], inFile: Optional[PathOrStr] = None
    ) -> None:
        super().__init__(fileType)

        if inFile:
            self._path = Path(inFile)
            self._name = self._path.name
            self._parse(self._path)

    def _set_index_col(self, data):
        for dcol in ["datetime", "*"]:
            if dcol in data.columns.values:
                data["date"] = pd.to_datetime(data[dcol]).dt.date
                data = data.set_index("date")
                del data[dcol]
        return data

    def _parse(
        self,
        inFile: PathOrStr,
        skip_header: bool = False,
        daily: bool = False,
        vars: Optional[List[str]] = None,
    ) -> None:
        fileInMem = io.StringIO(Path(inFile).read_text())

        if skip_header:
            for line in fileInMem:
                if "%data" in line:
                    break

        data = pd.read_csv(fileInMem, sep="\t")
        data = self._set_index_col(data)
        if vars:
            data = data[vars]
        self._data = data
        self._path = Path(inFile)
        self._name = Path(inFile).name


class AirchemParser(TxtParser):
    _fileType = InFile.AIRCHEM

    def __init__(self, inFile: Optional[PathOrStr] = None) -> None:
        super().__init__(self._fileType)
        if inFile:
            self.parse(inFile)

    def parse(self, inFile: PathOrStr, vars: Optional[List[str]] = None) -> None:
        self._parse(inFile, skip_header=True, vars=vars)


class ClimateParser(TxtParser):
    _fileType = InFile.CLIMATE

    def __init__(self, inFile: Optional[PathOrStr] = None, **kwargs) -> None:
        super().__init__(self._fileType)
        if inFile:
            self.parse(inFile, **kwargs)

    def parse(self, inFile: PathOrStr, vars: Optional[List[str]] = None) -> None:
        """parse climate file (optional: selection of vars)"""
        self._parse(inFile, skip_header=True, daily=True, vars=vars)

    def encode(self, vars=None):
        cols = self._data.columns.values
        if vars:
            cols = [v for v in vars if v in cols]


class SiteParser(XmlParser):
    _fileType = InFile.SITE

    def __init__(self, inFile: Optional[PathOrStr] = None) -> None:
        super().__init__(self._fileType)
        if inFile:
            self.parse(inFile)

    def _parse(self, inFile: PathOrStr, id: Optional[str] = None) -> None:
        root = ET.parse(Path(inFile)).getroot()

        sites = root.findall("./site")

        if id:
            for site in sites:
                if site.id == id:
                    break
        else:
            site = sites[0]

        self._data = site.find("./soil")
        self._path = Path(inFile)
        self._name = Path(inFile).name

    def parse(self, inFile: PathOrStr, id: Optional[str] = None) -> None:
        self._parse(inFile, id=id)


# ---


class DailyResultsParser(TxtParser):
    _fileType = OutFile.DAILY

    def __init__(self, inFile: Optional[PathOrStr] = None, **kwargs) -> None:
        super().__init__(self._fileType)
        if inFile:
            self.parse(inFile, **kwargs)

    @property
    def data_nounits(self):
        self._data.columns = (
            pd.Series(self._data.columns.values).str.replace(r"\[.*\]", "").values
        )
        return self._data

    def parse(
        self,
        inFile: PathOrStr,
        vars: Optional[List[str]] = None,
        ids: Optional[List[int]] = None,
    ) -> None:
        """parse daily result file (optional: selection of vars)"""
        # since we want to catch multi-id files we select vars at the end and not in _parse
        self._parse(inFile, daily=True)
        if ids:
            ids_present = np.unique(self._data.id.values)
            if set(ids).issubset(set(ids_present)):
                self._data = self._data[self._data.id.isin(ids)]
            else:
                print(f"IDs not in file: requested: {ids}; present: {ids_present}")
        if vars:
            self._data = self._data[vars]

    def encode(self, vars=None):
        cols = self._data.columns.values
        if vars:
            cols = [v for v in vars if v in cols]


# factory
class Parser:
    """a parser factory for a set of dndc file types"""

    # TODO: add an option to "sense" the file by parsing the optionally provided file name
    parsers = [AirchemParser, ClimateParser, SiteParser, DailyResultsParser]

    def __new__(
        self, fileType: InFile, inFile: Optional[PathOrStr] = None, **kwargs
    ) -> InFile:
        matched_parsers = [r for r in self.parsers if r.is_parser_for(fileType)]
        if len(matched_parsers) == 1:
            return matched_parsers[0](inFile, **kwargs)
        elif len(matched_parsers) > 1:
            print("Multiple parsers matched. Something is very wrong here!")
        else:
            raise NotImplementedError
