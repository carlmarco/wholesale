"""
Matching dentists to the buildings they practise in.

Two sources have to be joined and neither was designed for it. Licensure records
carry the address a dentist practises at, suite and all. Tax rolls carry the
address of a parcel. The same building is written differently in each - "1234
North Orange Avenue, Suite 200" against "1234 N ORANGE AVE" - so both sides are
reduced to a canonical key before comparison.

Stripping the suite is deliberate and is the point of the exercise. The dentist
occupies a suite; the parcel is the whole building. Dropping the unit is what
lets a licensee find their building at all, and when several dentists reduce to
one key that is a finding rather than a collision: a multi-practitioner building.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from src.wholesaler.transformers.address_standardizer import AddressStandardizer
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)

_standardizer = AddressStandardizer()

# Everything from a unit designator onward describes space inside the building,
# not the building, so it is removed before matching.
_UNIT_MARKERS = (
    "SUITE", "STE", "UNIT", "APT", "APARTMENT", "BLDG", "BUILDING",
    "FLOOR", "FL", "ROOM", "RM", "OFFICE", "OFC", "#",
)
_UNIT_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(marker) for marker in _UNIT_MARKERS) + r")\b.*$"
)
_HASH_PATTERN = re.compile(r"#.*$")
_PUNCTUATION = re.compile(r"[.,;:'\"]")
_WHITESPACE = re.compile(r"\s+")

# Names that mark an owning entity as a dental practice rather than a landlord.
DENTAL_NAME_MARKERS = (
    "DDS", "DMD", "DENTAL", "DENTISTRY", "DENTIST", "ORTHODONT", "PERIODONT",
    "ENDODONT", "PROSTHODONT", "ORAL SURG", "ORAL AND MAXILLOFACIAL", "PEDIATRIC DENT",
)

# Entity suffixes carry no identifying information when comparing owner names.
_ENTITY_NOISE = (
    "LLC", "L L C", "INC", "PA", "P A", "PLLC", "P L L C", "CORP", "CORPORATION",
    "COMPANY", "CO", "LTD", "LP", "LLP", "TRUST", "TR", "REVOCABLE", "LIVING",
    "FAMILY", "ET AL", "TRUSTEE", "TTEE",
)


def normalize_street(street: str) -> str:
    """
    Reduce a street address to a comparable form.

    Removes unit designators, punctuation and case, and applies the same
    directional and suffix abbreviations to both sources so that "North Orange
    Avenue" and "N ORANGE AVE" agree.

    Args:
        street: A street address from either source.

    Returns:
        The canonical form, or an empty string if nothing usable remains.
    """
    if not street:
        return ""

    text = _PUNCTUATION.sub(" ", str(street).upper())
    text = _HASH_PATTERN.sub(" ", text)
    text = _UNIT_PATTERN.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()

    if not text:
        return ""

    words = []
    for word in text.split(" "):
        word = _standardizer.DIRECTIONS.get(word, word)
        word = _standardizer.STREET_TYPES.get(word, word)
        words.append(word)

    return " ".join(words)


def normalize_zip(zip_code: Optional[str]) -> str:
    """Reduce a ZIP to its five-digit form; ZIP+4 differs between sources."""
    if not zip_code:
        return ""
    digits = re.sub(r"\D", "", str(zip_code))
    return digits[:5] if len(digits) >= 5 else ""


def address_match_key(street: str, zip_code: Optional[str]) -> Optional[str]:
    """
    Build the key both sources are joined on.

    ZIP is included because street names repeat across a state: there is a
    "MAIN ST" in most Florida cities, and matching statewide on street alone
    would merge unrelated buildings.

    Args:
        street: Street address.
        zip_code: Postal code, five digits or ZIP+4.

    Returns:
        A key of the form ``"1234 N ORANGE AVE|32801"``, or None when either
        half is missing - a partial key would match far too much.
    """
    normalized = normalize_street(street)
    postal = normalize_zip(zip_code)
    if not normalized or not postal:
        return None
    return f"{normalized}|{postal}"


def normalize_person_name(name: str) -> str:
    """Reduce a personal name to comparable words, dropping titles and initials."""
    if not name:
        return ""
    text = _PUNCTUATION.sub(" ", str(name).upper())
    words = [word for word in _WHITESPACE.sub(" ", text).split(" ") if len(word) > 1]
    return " ".join(word for word in words if word not in {"DR", "MR", "MRS", "MS"})


def normalize_entity_name(name: str) -> str:
    """Reduce an owning entity's name, dropping incorporation boilerplate."""
    if not name:
        return ""
    text = _PUNCTUATION.sub(" ", str(name).upper())
    words = _WHITESPACE.sub(" ", text).split(" ")
    return " ".join(word for word in words if word and word not in _ENTITY_NOISE)


def looks_like_dental_entity(owner_name: str) -> bool:
    """Whether an owner name identifies itself as a dental practice."""
    if not owner_name:
        return False
    upper = str(owner_name).upper()
    return any(marker in upper for marker in DENTAL_NAME_MARKERS)


def owner_matches_dentist(owner_name: str, dentist_last_name: str) -> bool:
    """
    Whether a parcel's owner appears to be the practising dentist.

    Two ways this shows up in tax rolls: the dentist owns personally, so their
    surname appears in the owner name; or they own through a practice entity
    that names itself dentally. Both are treated as owner-occupied, since either
    means the person to approach is the dentist rather than a third-party
    landlord.

    Args:
        owner_name: Owner of record from the tax roll.
        dentist_last_name: The licensee's surname.

    Returns:
        True when the owner looks like the dentist or their practice.
    """
    if not owner_name:
        return False

    if looks_like_dental_entity(owner_name):
        return True

    if not dentist_last_name:
        return False

    surname = normalize_person_name(dentist_last_name)
    if not surname:
        return False

    return surname in normalize_entity_name(owner_name).split(" ")


@dataclass(frozen=True)
class AddressMatch:
    """
    One building, with the licensees found at its address.

    Attributes:
        match_key: The canonical address both sides agreed on.
        parcel: The matched parcel.
        licensees: Every licensee resolving to this address.
        owner_occupied: Whether the owner of record looks like one of them.
    """
    match_key: str
    parcel: object
    licensees: Sequence[object]
    owner_occupied: bool

    @property
    def practitioner_count(self) -> int:
        return len(self.licensees)


def index_by_address(records: Iterable[object], street_attr: str, zip_attr: str) -> Dict[str, List[object]]:
    """
    Group records by their address key.

    Args:
        records: Objects carrying a street and ZIP attribute.
        street_attr: Attribute holding the street address.
        zip_attr: Attribute holding the ZIP.

    Returns:
        Address key to the records sharing it. Records without a usable key are
        omitted; callers compare counts to see how many were dropped.
    """
    index: Dict[str, List[object]] = defaultdict(list)
    for record in records:
        key = address_match_key(getattr(record, street_attr, ""), getattr(record, zip_attr, ""))
        if key:
            index[key].append(record)
    return dict(index)


def match_licensees_to_parcels(
    licensees: Sequence[object],
    parcels: Sequence[object],
) -> List[AddressMatch]:
    """
    Join licensees to the parcels they practise on.

    Args:
        licensees: Records with ``practice_street``, ``practice_zip`` and
            ``last_name``.
        parcels: Records with ``site_street``, ``site_zip`` and ``owner_name``.

    Returns:
        One match per parcel that at least one licensee resolved to, ordered by
        practitioner count so the busiest buildings come first.
    """
    licensees_by_address = index_by_address(licensees, "practice_street", "practice_zip")
    parcels_by_address = index_by_address(parcels, "site_street", "site_zip")

    matches: List[AddressMatch] = []
    for key, matched_parcels in parcels_by_address.items():
        found = licensees_by_address.get(key)
        if not found:
            continue

        for parcel in matched_parcels:
            owner_name = getattr(parcel, "owner_name", "") or ""
            occupied = any(
                owner_matches_dentist(owner_name, getattr(licensee, "last_name", ""))
                for licensee in found
            )
            matches.append(
                AddressMatch(
                    match_key=key,
                    parcel=parcel,
                    licensees=tuple(found),
                    owner_occupied=occupied,
                )
            )

    matches.sort(key=lambda match: match.practitioner_count, reverse=True)

    logger.info(
        "licensees_matched_to_parcels",
        licensee_addresses=len(licensees_by_address),
        parcel_addresses=len(parcels_by_address),
        matched=len(matches),
    )
    return matches
