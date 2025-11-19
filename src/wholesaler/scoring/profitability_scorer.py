"""
Profitability scoring components for the wholesaler application.

This module implements the "Conservative Profitability Guardrails" defined in Phase 3.6.
It ensures that leads are only surfaced if they meet strict profit margin criteria.
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional
from config.settings import settings

@dataclass
class ProfitabilityResult:
    """Result of a profitability calculation."""
    projected_profit: float
    roi_percent: float
    is_profitable: bool
    details: Dict[str, float]


class ConservativeProfitabilityBucket:
    """
    Profitability guardrail scorer.
    
    Logic:
    Projected Profit = (ARV * 0.70) - Repairs - Acquisition
    
    Must be > settings.profitability_min_profit (default $15k) to be considered profitable.
    """
    
    # Default assumptions if data is missing
    DEFAULT_REPAIR_COST_SQFT = 25.0  # $/sqft for cosmetic rehab
    MIN_REPAIR_COST = 15000.0        # Minimum repair budget
    ARV_RATIO = 0.70                 # 70% Rule
    MIN_PROFIT_THRESHOLD = 15000.0   # Minimum profit to be actionable

    def score(self, record: Dict[str, Any]) -> ProfitabilityResult:
        """
        Calculate profitability metrics for a property record.
        
        Args:
            record: Enriched property record dictionary
            
        Returns:
            ProfitabilityResult object
        """
        # 1. Determine ARV (After Repair Value)
        # Use ML prediction if available, otherwise fallback to market value or assessed value * 1.2
        arv = self._estimate_arv(record)
        
        # 2. Estimate Repair Costs
        repair_costs = self._estimate_repair_costs(record)
        
        # 3. Determine Acquisition Cost
        # For tax sales: opening bid or taxes owed
        # For foreclosures: default amount or opening bid
        # For others: assume we need to offer 50-60% of ARV to make it work, 
        # but for the "test", we check if the *current* implied cost (e.g. debt) allows room.
        # If no debt info, we calculate "Max Allowable Offer" (MAO) instead of profit.
        # However, to fit the "Guardrail" concept, we often check if the *Asking/Debt* price works.
        acquisition_cost = self._estimate_acquisition_cost(record)
        
        # 4. Calculate Profit
        # Profit = (ARV * 0.70) - Repairs - Acquisition
        # Note: The 0.70 factor typically includes holding costs, closing costs, and investor profit.
        # So "Projected Profit" here is the *Wholesaler's Spread* if we treat the 0.70 as the end-buyer's buy box.
        # Let's refine: End Buyer pays (ARV * 0.70 - Repairs). 
        # Wholesaler Profit = (End Buyer Price) - Acquisition Cost.
        
        end_buyer_price = (arv * self.ARV_RATIO) - repair_costs
        projected_profit = end_buyer_price - acquisition_cost
        
        # ROI Calculation (Profit / Total Investment)
        # Total Investment = Acquisition + Repairs (simplified)
        total_investment = acquisition_cost + repair_costs
        roi = (projected_profit / total_investment * 100) if total_investment > 0 else 0.0
        
        is_profitable = projected_profit >= self.MIN_PROFIT_THRESHOLD
        
        return ProfitabilityResult(
            projected_profit=round(projected_profit, 2),
            is_profitable=is_profitable,
            roi_percent=round(roi, 2),
            details={
                "arv": round(arv, 2),
                "repair_costs": round(repair_costs, 2),
                "acquisition_cost": round(acquisition_cost, 2),
                "end_buyer_price": round(end_buyer_price, 2),
                "max_allowable_offer": round(end_buyer_price - self.MIN_PROFIT_THRESHOLD, 2)
            }
        )

    def _estimate_arv(self, record: Dict[str, Any]) -> float:
        """Estimate After Repair Value."""
        # Priority 1: ML Predicted ARV (if we had it)
        if record.get("ml_arv"):
            return float(record["ml_arv"])
            
        # Priority 2: Property Record Market Value
        # Market value in public records is often lagged/conservative. 
        # We might apply a small multiplier (e.g. 1.1) or take it as is.
        prop_record = record.get("property_record") or {}
        total_mkt = prop_record.get("total_mkt") or record.get("total_mkt")
        
        if total_mkt:
            return float(total_mkt)
            
        # Priority 3: Assessed Value * Multiplier
        assessed_val = prop_record.get("assessed_val")
        if assessed_val:
            return float(assessed_val) * 1.25
            
        return 0.0

    def _estimate_repair_costs(self, record: Dict[str, Any]) -> float:
        """Estimate Repair Costs based on sqft and distress signals."""
        prop_record = record.get("property_record") or {}
        sqft = prop_record.get("living_area") or record.get("living_area") or 1500 # default 1500
        
        # Base cost
        cost_per_sqft = self.DEFAULT_REPAIR_COST_SQFT
        
        # Adjust for distress severity
        violation_count = record.get("violation_count") or 0
        if violation_count > 5:
            cost_per_sqft += 15.0 # Heavy distress
        elif violation_count > 0:
            cost_per_sqft += 5.0  # Light distress
            
        # Adjust for age
        year_built = prop_record.get("year_built")
        if year_built and year_built < 1980:
            cost_per_sqft += 10.0
            
        total_repairs = float(sqft) * cost_per_sqft
        return max(total_repairs, self.MIN_REPAIR_COST)

    def _estimate_acquisition_cost(self, record: Dict[str, Any]) -> float:
        """Estimate acquisition cost based on seed type."""
        # If Tax Sale: Use opening bid or taxes owed
        tax_sale = record.get("tax_sale") or {}
        if tax_sale.get("opening_bid"):
            return float(tax_sale["opening_bid"])
            
        # If Foreclosure: Use default amount (judgment amount)
        foreclosure = record.get("foreclosure") or {}
        if foreclosure.get("default_amount"):
            return float(foreclosure["default_amount"])
        if foreclosure.get("opening_bid"):
            return float(foreclosure["opening_bid"])
            
        # If just a lead (Code Violation), we don't have a set "price".
        # In this case, we assume we can negotiate. 
        # But for the purpose of the *Guardrail*, we check if there's implied debt.
        # If no debt known, we assume Acquisition = 0 for the calculation 
        # (which means 'projected_profit' becomes MAO).
        # BUT, to be conservative, let's assume we pay 50% of Market Value if no other data.
        arv = self._estimate_arv(record)
        return arv * 0.50
