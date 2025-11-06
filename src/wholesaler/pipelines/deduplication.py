"""
Data Deduplication Pipeline

Merges property records from multiple sources by parcel ID.
"""
from typing import List, Dict, Optional
from collections import defaultdict

from src.wholesaler.utils.logger import get_logger
from src.wholesaler.models.property import TaxSaleProperty, EnrichedProperty
from src.wholesaler.models.foreclosure import ForeclosureProperty
from src.wholesaler.models.property_record import PropertyRecord
from src.wholesaler.transformers.address_standardizer import AddressStandardizer

logger = get_logger(__name__)


class PropertyDeduplicator:
    """
    Deduplicates and merges property records from multiple sources.

    Uses normalized parcel IDs as the primary key for merging.
    """

    def __init__(self):
        """Initialize deduplicator with address standardizer."""
        self.standardizer = AddressStandardizer()
        logger.info("property_deduplicator_initialized")

    def merge_sources(
        self,
        tax_sales: Optional[List[TaxSaleProperty]] = None,
        foreclosures: Optional[List[ForeclosureProperty]] = None,
        property_records: Optional[List[PropertyRecord]] = None,
        enriched_properties: Optional[List[EnrichedProperty]] = None
    ) -> List[Dict]:
        """
        Merge property data from multiple sources by parcel ID.

        Args:
            tax_sales: Tax sale properties
            foreclosures: Foreclosure properties
            property_records: Property appraiser records
            enriched_properties: Properties with geographic enrichment

        Returns:
            List of merged property dictionaries
        """
        logger.info(
            "starting_merge",
            tax_sales=len(tax_sales) if tax_sales else 0,
            foreclosures=len(foreclosures) if foreclosures else 0,
            property_records=len(property_records) if property_records else 0,
            enriched=len(enriched_properties) if enriched_properties else 0
        )

        # Index by normalized parcel ID
        parcel_index: Dict[str, Dict] = defaultdict(dict)

        # Process each source
        if tax_sales:
            self._index_tax_sales(parcel_index, tax_sales)

        if foreclosures:
            self._index_foreclosures(parcel_index, foreclosures)

        if property_records:
            self._index_property_records(parcel_index, property_records)

        if enriched_properties:
            self._index_enriched_properties(parcel_index, enriched_properties)

        # Convert to list
        merged = list(parcel_index.values())

        logger.info(
            "merge_complete",
            unique_parcels=len(merged),
            with_tax_sale=sum(1 for m in merged if 'tax_sale' in m),
            with_foreclosure=sum(1 for m in merged if 'foreclosure' in m),
            with_valuation=sum(1 for m in merged if 'property_record' in m)
        )

        return merged

    def _index_tax_sales(self, index: Dict, tax_sales: List[TaxSaleProperty]):
        """Add tax sale data to index."""
        for prop in tax_sales:
            if not prop.parcel_id:
                continue

            normalized_parcel = self.standardizer.normalize_parcel_id(prop.parcel_id)
            if not normalized_parcel:
                continue

            if 'parcel_id_normalized' not in index[normalized_parcel]:
                index[normalized_parcel]['parcel_id_normalized'] = normalized_parcel
                index[normalized_parcel]['parcel_id_original'] = prop.parcel_id

            index[normalized_parcel]['tax_sale'] = {
                'tda_number': prop.tda_number,
                'sale_date': prop.sale_date,
                'deed_status': prop.deed_status,
                'latitude': prop.latitude,
                'longitude': prop.longitude
            }

    def _index_foreclosures(self, index: Dict, foreclosures: List[ForeclosureProperty]):
        """Add foreclosure data to index."""
        for prop in foreclosures:
            if not prop.parcel_number:
                continue

            normalized_parcel = self.standardizer.normalize_parcel_id(prop.parcel_number)
            if not normalized_parcel:
                continue

            if 'parcel_id_normalized' not in index[normalized_parcel]:
                index[normalized_parcel]['parcel_id_normalized'] = normalized_parcel
                index[normalized_parcel]['parcel_id_original'] = prop.parcel_number

            index[normalized_parcel]['foreclosure'] = {
                'borrowers_name': prop.borrowers_name,
                'situs_address': prop.situs_address,
                'default_amount': prop.default_amount,
                'opening_bid': prop.opening_bid,
                'auction_date': prop.auction_date,
                'lender_name': prop.lender_name,
                'property_type': prop.property_type,
                'latitude': prop.latitude,
                'longitude': prop.longitude
            }

    def _index_property_records(self, index: Dict, property_records: List[PropertyRecord]):
        """Add property appraiser data to index."""
        for prop in property_records:
            if not prop.parcel_number:
                continue

            normalized_parcel = self.standardizer.normalize_parcel_id(prop.parcel_number)
            if not normalized_parcel:
                continue

            if 'parcel_id_normalized' not in index[normalized_parcel]:
                index[normalized_parcel]['parcel_id_normalized'] = normalized_parcel
                index[normalized_parcel]['parcel_id_original'] = prop.parcel_number

            index[normalized_parcel]['property_record'] = {
                'situs_address': prop.situs_address,
                'owner_name': prop.owner_name,
                'total_mkt': prop.total_mkt,
                'total_assd': prop.total_assd,
                'taxable': prop.taxable,
                'taxes': prop.taxes,
                'year_built': prop.year_built,
                'living_area': prop.living_area,
                'lot_size': prop.lot_size,
                'equity_percent': prop.calculate_equity_percent(),
                'tax_rate': prop.calculate_tax_rate(),
                'latitude': prop.latitude,
                'longitude': prop.longitude
            }

    def _index_enriched_properties(self, index: Dict, enriched: List[EnrichedProperty]):
        """Add geographic enrichment data to index."""
        for prop in enriched:
            if not prop.parcel_id:
                continue

            normalized_parcel = self.standardizer.normalize_parcel_id(prop.parcel_id)
            if not normalized_parcel:
                continue

            if 'parcel_id_normalized' not in index[normalized_parcel]:
                index[normalized_parcel]['parcel_id_normalized'] = normalized_parcel
                index[normalized_parcel]['parcel_id_original'] = prop.parcel_id

            index[normalized_parcel]['enrichment'] = {
                'nearby_violations': prop.nearby_violations,
                'nearby_open_violations': prop.nearby_open_violations,
                'nearest_violation_distance': prop.nearest_violation_distance,
                'avg_violation_distance': prop.avg_violation_distance,
                'violation_types_nearby': prop.violation_types_nearby
            }

    def find_duplicates(self, properties: List[Dict], by_address: bool = False) -> Dict[str, List[Dict]]:
        """
        Find duplicate properties by parcel ID or address.

        Args:
            properties: List of property dictionaries
            by_address: If True, group by address instead of parcel

        Returns:
            Dictionary mapping key -> list of duplicate properties
        """
        groups = defaultdict(list)

        for prop in properties:
            if by_address:
                address = prop.get('situs_address', '')
                if address:
                    key = address.upper().strip()
                    groups[key].append(prop)
            else:
                parcel = prop.get('parcel_id_normalized') or prop.get('parcel_id_original')
                if parcel:
                    normalized = self.standardizer.normalize_parcel_id(parcel)
                    if normalized:
                        groups[normalized].append(prop)

        # Only return groups with multiple entries
        duplicates = {k: v for k, v in groups.items() if len(v) > 1}

        logger.info(
            "duplicates_found",
            total_properties=len(properties),
            duplicate_groups=len(duplicates),
            by_address=by_address
        )

        return duplicates

    def resolve_coordinates(self, merged_property: Dict) -> tuple[Optional[float], Optional[float]]:
        """
        Resolve best coordinates from merged property sources.

        Priority: property_record > foreclosure > tax_sale > enrichment

        Args:
            merged_property: Merged property dictionary

        Returns:
            Tuple of (latitude, longitude) or (None, None)
        """
        sources = ['property_record', 'foreclosure', 'tax_sale', 'enrichment']

        for source in sources:
            if source in merged_property:
                lat = merged_property[source].get('latitude')
                lon = merged_property[source].get('longitude')
                if lat and lon:
                    return lat, lon

        return None, None
