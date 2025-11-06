"""
Address Standardization Transformer

Normalizes and standardizes property addresses across different data sources.
"""
import re
from typing import Optional
from dataclasses import dataclass

from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class StandardizedAddress:
    """
    Standardized address components.

    Attributes:
        street_number: House/building number
        street_name: Street name (normalized)
        street_type: Street type (ST, AVE, RD, etc.)
        unit_type: Unit type (APT, UNIT, STE, etc.)
        unit_number: Unit number
        city: City name
        state: State abbreviation
        zip_code: 5-digit ZIP code
        full_address: Complete standardized address
    """
    street_number: Optional[str] = None
    street_name: Optional[str] = None
    street_type: Optional[str] = None
    unit_type: Optional[str] = None
    unit_number: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    full_address: Optional[str] = None


class AddressStandardizer:
    """
    Standardizes addresses to a consistent format across data sources.

    Handles common variations, abbreviations, and formatting inconsistencies.
    """

    # Street type abbreviations
    STREET_TYPES = {
        'ALLEY': 'ALY', 'AVENUE': 'AVE', 'BOULEVARD': 'BLVD', 'CIRCLE': 'CIR',
        'COURT': 'CT', 'DRIVE': 'DR', 'EXPRESSWAY': 'EXPY', 'HIGHWAY': 'HWY',
        'LANE': 'LN', 'PARKWAY': 'PKWY', 'PLACE': 'PL', 'ROAD': 'RD',
        'STREET': 'ST', 'TERRACE': 'TER', 'TRAIL': 'TRL', 'WAY': 'WAY',
        'LOOP': 'LOOP', 'PATH': 'PATH', 'PIKE': 'PIKE', 'PLAZA': 'PLZ',
        'POINT': 'PT', 'RIDGE': 'RDG', 'RUN': 'RUN', 'SQUARE': 'SQ'
    }

    # Unit type abbreviations
    UNIT_TYPES = {
        'APARTMENT': 'APT', 'BUILDING': 'BLDG', 'FLOOR': 'FL',
        'SUITE': 'STE', 'UNIT': 'UNIT', 'ROOM': 'RM', '#': 'UNIT'
    }

    # Directional abbreviations
    DIRECTIONS = {
        'NORTH': 'N', 'SOUTH': 'S', 'EAST': 'E', 'WEST': 'W',
        'NORTHEAST': 'NE', 'NORTHWEST': 'NW', 'SOUTHEAST': 'SE', 'SOUTHWEST': 'SW'
    }

    def __init__(self):
        """Initialize address standardizer."""
        logger.info("address_standardizer_initialized")

    def standardize(self, address: str, city: Optional[str] = None,
                   state: Optional[str] = None, zip_code: Optional[str] = None) -> StandardizedAddress:
        """
        Standardize a street address.

        Args:
            address: Raw street address
            city: City name
            state: State abbreviation
            zip_code: ZIP code

        Returns:
            StandardizedAddress with normalized components
        """
        if not address:
            logger.debug("empty_address_provided")
            return StandardizedAddress()

        # Clean and normalize
        address = address.strip().upper()

        # Extract unit information
        unit_type, unit_number, address = self._extract_unit(address)

        # Parse street components
        street_number, street_name, street_type = self._parse_street(address)

        # Normalize city and state
        city_norm = city.strip().upper() if city else None
        state_norm = state.strip().upper() if state else None
        zip_norm = self._normalize_zip(zip_code) if zip_code else None

        # Build full address
        full_address = self._build_full_address(
            street_number, street_name, street_type,
            unit_type, unit_number, city_norm, state_norm, zip_norm
        )

        result = StandardizedAddress(
            street_number=street_number,
            street_name=street_name,
            street_type=street_type,
            unit_type=unit_type,
            unit_number=unit_number,
            city=city_norm,
            state=state_norm,
            zip_code=zip_norm,
            full_address=full_address
        )

        logger.debug(
            "address_standardized",
            original=address[:50],
            standardized=full_address[:50] if full_address else None
        )

        return result

    def _extract_unit(self, address: str) -> tuple[Optional[str], Optional[str], str]:
        """
        Extract unit information from address.

        Returns:
            Tuple of (unit_type, unit_number, remaining_address)
        """
        # Pattern: # 123, APT 123, UNIT 123, STE 123
        unit_pattern = r'(#|APT|APARTMENT|UNIT|SUITE|STE|BLDG|BUILDING|FL|FLOOR|RM|ROOM)\s*([A-Z0-9\-]+)'

        match = re.search(unit_pattern, address)
        if match:
            unit_type_raw = match.group(1)
            unit_number = match.group(2)

            # Standardize unit type
            unit_type = self.UNIT_TYPES.get(unit_type_raw, unit_type_raw)

            # Remove unit from address
            address = address[:match.start()] + address[match.end():]
            address = address.strip()

            return unit_type, unit_number, address

        return None, None, address

    def _parse_street(self, address: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Parse street components from address.

        Returns:
            Tuple of (street_number, street_name, street_type)
        """
        # Remove extra spaces
        address = ' '.join(address.split())

        parts = address.split()
        if not parts:
            return None, None, None

        # First part is usually street number
        street_number = None
        if parts[0].replace('-', '').isdigit():
            street_number = parts[0]
            parts = parts[1:]

        if not parts:
            return street_number, None, None

        # Last part might be street type
        street_type = None
        if parts[-1] in self.STREET_TYPES or parts[-1] in self.STREET_TYPES.values():
            street_type_raw = parts[-1]
            street_type = self.STREET_TYPES.get(street_type_raw, street_type_raw)
            parts = parts[:-1]

        # Remaining is street name with possible directional prefixes
        street_name_parts = []
        for part in parts:
            # Normalize directional
            if part in self.DIRECTIONS:
                street_name_parts.append(self.DIRECTIONS[part])
            elif part in self.DIRECTIONS.values():
                street_name_parts.append(part)
            else:
                street_name_parts.append(part)

        street_name = ' '.join(street_name_parts) if street_name_parts else None

        return street_number, street_name, street_type

    @staticmethod
    def _normalize_zip(zip_code: str) -> Optional[str]:
        """
        Normalize ZIP code to 5 digits.

        Args:
            zip_code: Raw ZIP code

        Returns:
            5-digit ZIP code or None
        """
        if not zip_code:
            return None

        # Extract digits
        digits = re.sub(r'\D', '', str(zip_code))

        # Return first 5 digits
        if len(digits) >= 5:
            return digits[:5]

        return None

    @staticmethod
    def _build_full_address(street_number: Optional[str], street_name: Optional[str],
                           street_type: Optional[str], unit_type: Optional[str],
                           unit_number: Optional[str], city: Optional[str],
                           state: Optional[str], zip_code: Optional[str]) -> Optional[str]:
        """
        Build standardized full address string.

        Returns:
            Complete standardized address or None
        """
        parts = []

        # Street address
        if street_number:
            parts.append(street_number)
        if street_name:
            parts.append(street_name)
        if street_type:
            parts.append(street_type)

        street_address = ' '.join(parts) if parts else None

        # Unit
        unit_address = None
        if unit_type and unit_number:
            unit_address = f"{unit_type} {unit_number}"

        # City, State, ZIP
        location_parts = []
        if city:
            location_parts.append(city)
        if state:
            location_parts.append(state)
        if zip_code:
            location_parts.append(zip_code)

        location = ', '.join(location_parts) if location_parts else None

        # Combine all parts
        full_parts = []
        if street_address:
            full_parts.append(street_address)
        if unit_address:
            full_parts.append(unit_address)
        if location:
            full_parts.append(location)

        return ', '.join(full_parts) if full_parts else None

    def normalize_parcel_id(self, parcel_id: str) -> Optional[str]:
        """
        Normalize parcel ID by removing formatting characters.

        Args:
            parcel_id: Raw parcel ID

        Returns:
            Normalized parcel ID (digits only)
        """
        if not parcel_id:
            return None

        # Remove all non-digit characters
        normalized = re.sub(r'\D', '', str(parcel_id))

        return normalized if normalized else None
