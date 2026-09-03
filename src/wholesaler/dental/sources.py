"""
Reading the two public files this rests on.

**Licensees** come from the Florida Department of Health's Medical Quality
Assurance data download: every licence in the state, pipe-delimited, refreshed
daily, free. Filtered to dentistry it gives licence number, name, practice
address, licence date and status - and licence date is the age proxy the whole
dental model depends on.

**Parcels** come from the Department of Revenue's annual NAL tax rolls, one file
per county per year. DOR use code 0019, "Professional Services Buildings", is
the code medical and dental offices sit under and is how the universe is found
at all.

Neither file has a stable published column order, and county roll extracts get
re-exported with renamed headers, so columns are resolved by trying the spellings
each source is known to use rather than by position.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, TextIO

from src.wholesaler.transformers.address_standardizer import AddressStandardizer
from src.wholesaler.utils.dates import coerce_date
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

_standardizer = AddressStandardizer()

# DOR use codes carrying medical and dental offices. 0019 is the professional
# services code; 0018 and 0017 are general office, kept as a wider net because
# some counties code standalone dental buildings there.
PROFESSIONAL_SERVICES_USE_CODE = "0019"
DEFAULT_USE_CODES = ("0019",)
WIDER_OFFICE_USE_CODES = ("0017", "0018", "0019")

# Licences that are not currently practising are not leads, but they are still
# counted so the report can show how much of the file was excluded.
ACTIVE_STATUSES = {"ACTIVE", "CLEAR", "CLEAR/ACTIVE", "ACTIVE IN GOOD STANDING"}


@dataclass(frozen=True)
class DentistLicense:
    """
    One dental licence.

    Attributes:
        license_number: State licence identifier.
        last_name: Surname, used to test whether a parcel owner is the dentist.
        full_name: Name as published.
        license_date: Original issue date - the age proxy.
        status: Licence status as published.
        practice_street: Practice street address, suite included.
        practice_city: Practice city.
        practice_zip: Practice ZIP.
        county: County as published, when present.
    """
    license_number: str
    last_name: str
    full_name: str
    license_date: Optional[date]
    status: str
    practice_street: str
    practice_city: str
    practice_zip: str
    county: str = ""

    @property
    def is_active(self) -> bool:
        return self.status.strip().upper() in ACTIVE_STATUSES

    def years_licensed(self, as_of: Optional[date] = None) -> Optional[float]:
        """Years since issue, the proxy for how close this dentist is to exiting."""
        if self.license_date is None:
            return None
        return ((as_of or date.today()) - self.license_date).days / 365.25


@dataclass(frozen=True)
class DentalParcel:
    """
    One parcel from a tax roll, already filtered to an office use code.

    Attributes:
        parcel_id_normalized: Digits-only parcel identifier, the join key.
        parcel_id_original: Identifier as published.
        dor_use_code: Roll use code.
        owner_name: Owner of record.
        site_street: Situs street address.
        site_city: Situs city.
        site_zip: Situs ZIP.
        county: County the roll covers.
        roll_year: Year the values were certified for.
        just_value: Certified just/market value.
        building_sqft: Heated or total building area.
        year_built: Year of construction.
        last_sale_date: Most recent recorded sale, when the roll carries one.
        last_sale_price: Price of that sale.
    """
    parcel_id_normalized: str
    parcel_id_original: str
    dor_use_code: str
    owner_name: str
    site_street: str
    site_city: str
    site_zip: str
    county: str = ""
    roll_year: Optional[int] = None
    just_value: Optional[float] = None
    building_sqft: Optional[float] = None
    year_built: Optional[int] = None
    last_sale_date: Optional[date] = None
    last_sale_price: Optional[float] = None


def _resolve(columns: Dict[str, str], *candidates: str) -> Optional[str]:
    """First candidate spelling present in the header."""
    for candidate in candidates:
        if candidate in columns:
            return columns[candidate]
    return None


def _text(row: Dict[str, str], column: Optional[str]) -> str:
    return (row.get(column) or "").strip() if column else ""


def _number(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    cleaned = str(raw).replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _open_delimited(handle: TextIO, delimiter: Optional[str]) -> csv.DictReader:
    """
    Read the file with its delimiter, sniffed when not stated.

    MQA downloads are pipe-delimited and county re-exports are usually CSV, so
    guessing wrong turns every row into one unusable column.
    """
    if delimiter:
        return csv.DictReader(handle, delimiter=delimiter)

    sample = handle.read(8192)
    handle.seek(0)
    guessed = "|" if sample.count("|") > sample.count(",") else ","
    return csv.DictReader(handle, delimiter=guessed)


def _iter_rows(path: Path, delimiter: Optional[str]) -> Iterator[tuple]:
    """Yield (row, lowercase column index) pairs."""
    if not path.exists():
        raise FileNotFoundError(f"No extract at {path}")

    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = _open_delimited(handle, delimiter)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header row")
        columns = {name.lower().strip(): name for name in reader.fieldnames if name}
        for row in reader:
            yield row, columns


def load_licensees(
    path: Path,
    delimiter: Optional[str] = None,
    active_only: bool = True,
) -> List[DentistLicense]:
    """
    Read dental licensees from an MQA data download.

    Args:
        path: The extract, filtered to dentistry before or after download.
        delimiter: Field separator; sniffed when omitted.
        active_only: Drop licences that are not currently practising.

    Returns:
        Parsed licences.

    Raises:
        FileNotFoundError: If the extract is absent.
        ValueError: If no licence number or name column can be found, which
            usually means a different profession's export was downloaded.
    """
    licensees: List[DentistLicense] = []
    skipped_unparseable = 0
    skipped_inactive = 0
    checked_header = False

    for row, columns in _iter_rows(path, delimiter):
        if not checked_header:
            if not _resolve(columns, "license_number", "licensenumber", "lic_number", "license no"):
                raise ValueError(
                    f"{path} has no licence number column; found {sorted(columns)[:12]}"
                )
            checked_header = True

        number = _text(row, _resolve(columns, "license_number", "licensenumber", "lic_number", "license no"))
        last_name = _text(row, _resolve(columns, "last_name", "lastname", "licensee_last_name"))
        full_name = _text(
            row, _resolve(columns, "full_name", "name", "licensee_name", "practitioner_name")
        )
        if not full_name and last_name:
            first = _text(row, _resolve(columns, "first_name", "firstname"))
            full_name = f"{first} {last_name}".strip()

        if not number or not (last_name or full_name):
            skipped_unparseable += 1
            continue

        if not last_name and full_name:
            last_name = full_name.replace(",", " ").split()[0]

        status = _text(row, _resolve(columns, "license_status", "status", "lic_status"))
        license_date = coerce_date(
            _text(
                row,
                _resolve(
                    columns,
                    "license_date",
                    "original_license_date",
                    "orig_license_date",
                    "issue_date",
                    "licensure_date",
                ),
            )
        )

        licence = DentistLicense(
            license_number=number,
            last_name=last_name,
            full_name=full_name or last_name,
            license_date=license_date,
            status=status,
            practice_street=_text(
                row,
                _resolve(
                    columns, "practice_address", "address_line_1", "addr_line_1",
                    "practice_street", "address1", "street",
                ),
            ),
            practice_city=_text(row, _resolve(columns, "practice_city", "city", "addr_city")),
            practice_zip=_text(row, _resolve(columns, "practice_zip", "zip", "zip_code", "addr_zip")),
            county=_text(row, _resolve(columns, "county", "practice_county", "county_name")),
        )

        if active_only and not licence.is_active:
            skipped_inactive += 1
            continue

        licensees.append(licence)

    logger.info(
        "licensees_loaded",
        path=str(path),
        loaded=len(licensees),
        skipped_inactive=skipped_inactive,
        skipped_unparseable=skipped_unparseable,
    )
    return licensees


def load_parcels(
    path: Path,
    use_codes: Sequence[str] = DEFAULT_USE_CODES,
    delimiter: Optional[str] = None,
    county: str = "",
) -> List[DentalParcel]:
    """
    Read office parcels from a NAL tax roll.

    Args:
        path: The roll extract.
        use_codes: Use codes to keep. Defaults to professional services only;
            pass WIDER_OFFICE_USE_CODES to include general office.
        delimiter: Field separator; sniffed when omitted.
        county: County label applied to every row, for rolls that omit it.

    Returns:
        Parcels carrying one of the requested use codes.

    Raises:
        FileNotFoundError: If the extract is absent.
        ValueError: If no parcel identifier column can be found.
    """
    wanted = {code.lstrip("0") or "0" for code in use_codes}
    parcels: List[DentalParcel] = []
    skipped_use_code = 0
    skipped_unparseable = 0
    checked_header = False

    for row, columns in _iter_rows(path, delimiter):
        parcel_column = _resolve(columns, "parcel_id", "parcel_id_normalized", "parcel", "folio", "pin")
        if not checked_header:
            if not parcel_column:
                raise ValueError(
                    f"{path} has no parcel identifier column; found {sorted(columns)[:12]}"
                )
            checked_header = True

        original = _text(row, parcel_column)
        normalized = _standardizer.normalize_parcel_id(original)
        if not normalized:
            skipped_unparseable += 1
            continue

        use_code = _text(row, _resolve(columns, "dor_uc", "dor_use_code", "use_code", "usecode"))
        if (use_code.lstrip("0") or "0") not in wanted:
            skipped_use_code += 1
            continue

        year_built = _number(
            _text(row, _resolve(columns, "act_yr_blt", "year_built", "eff_yr_blt", "actual_year_built"))
        )
        roll_year = _number(_text(row, _resolve(columns, "roll_year", "asmnt_yr", "tax_year", "year")))

        sale_date = coerce_date(_text(row, _resolve(columns, "sale_date", "last_sale_date", "sale_date1")))
        if sale_date is None:
            sale_year = _number(_text(row, _resolve(columns, "sale_yr1", "sale_year")))
            sale_month = _number(_text(row, _resolve(columns, "sale_mo1", "sale_month")))
            if sale_year and 1900 <= sale_year <= 2100:
                sale_date = date(int(sale_year), int(sale_month or 1) or 1, 1)

        parcels.append(
            DentalParcel(
                parcel_id_normalized=normalized,
                parcel_id_original=original,
                dor_use_code=use_code,
                owner_name=_text(row, _resolve(columns, "own_name", "owner_name", "owner")),
                site_street=_text(
                    row,
                    _resolve(columns, "phy_addr1", "site_address", "situs_address", "site_street", "address"),
                ),
                site_city=_text(row, _resolve(columns, "phy_city", "site_city", "situs_city", "city")),
                site_zip=_text(row, _resolve(columns, "phy_zipcd", "site_zip", "situs_zip", "zip")),
                county=_text(row, _resolve(columns, "co_no", "county", "county_name")) or county,
                roll_year=int(roll_year) if roll_year else None,
                just_value=_number(_text(row, _resolve(columns, "jv", "just_value", "total_mkt", "market_value"))),
                building_sqft=_number(
                    _text(row, _resolve(columns, "tot_lvg_ar", "building_sqft", "heated_area", "living_area"))
                ),
                year_built=int(year_built) if year_built else None,
                last_sale_date=sale_date,
                last_sale_price=_number(_text(row, _resolve(columns, "sale_prc1", "sale_price", "last_sale_price"))),
            )
        )

    logger.info(
        "parcels_loaded",
        path=str(path),
        loaded=len(parcels),
        skipped_use_code=skipped_use_code,
        skipped_unparseable=skipped_unparseable,
    )
    return parcels
