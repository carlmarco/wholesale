"""
Backward Compatibility Adapters

Helper functions to bridge between old and new code during migration.
"""
from typing import List, Dict
from src.wholesaler.models.property import TaxSaleProperty


def properties_to_dicts(properties: List[TaxSaleProperty]) -> List[Dict]:
    """
    Convert list of TaxSaleProperty instances to dictionaries.

    Used for backward compatibility with code expecting dict-based properties.

    Args:
        properties: List of TaxSaleProperty instances

    Returns:
        List of property dictionaries
    """
    return [prop.to_dict() for prop in properties]


def dict_to_property(property_dict: Dict) -> TaxSaleProperty:
    """
    Convert property dictionary to TaxSaleProperty instance.

    Args:
        property_dict: Property data as dictionary

    Returns:
        Validated TaxSaleProperty instance
    """
    return TaxSaleProperty(**property_dict)
