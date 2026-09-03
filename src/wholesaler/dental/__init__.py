"""
Dental office universe assembly.

Joins Florida's dental licensure file to county tax rolls to answer the question
everything else depends on: how many separately-parcelled dental buildings exist,
how many are owned by the dentist practising in them, and how many transact in a
year.

Nobody has that list assembled, which is the reason to build it. The output feeds
the dental_office scoring profile and, once sale outcomes are attached, the
feasibility harness.
"""
from src.wholesaler.dental.matching import (
    AddressMatch,
    address_match_key,
    looks_like_dental_entity,
    match_licensees_to_parcels,
    normalize_street,
    normalize_zip,
    owner_matches_dentist,
)
from src.wholesaler.dental.sources import (
    DEFAULT_USE_CODES,
    WIDER_OFFICE_USE_CODES,
    DentalParcel,
    DentistLicense,
    load_licensees,
    load_parcels,
)
from src.wholesaler.dental.universe import UniverseReport, measure_universe, render

__all__ = [
    "AddressMatch",
    "DEFAULT_USE_CODES",
    "DentalParcel",
    "DentistLicense",
    "UniverseReport",
    "WIDER_OFFICE_USE_CODES",
    "address_match_key",
    "load_licensees",
    "load_parcels",
    "looks_like_dental_entity",
    "match_licensees_to_parcels",
    "measure_universe",
    "normalize_street",
    "normalize_zip",
    "owner_matches_dentist",
    "render",
]
