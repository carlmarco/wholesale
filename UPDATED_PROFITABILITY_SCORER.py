# UPDATED_PROFITABILITY_SCORER.py

"""
Conservative Profitability Scorer for Nov 2025 Market Conditions

This module implements realistic, conservative profitability calculations
based on current housing market trends, repair cost inflation, and buyer
expectations. Constants have been updated from initial 2022-optimistic
assumptions to reflect 2025 market reality.

Key Changes from Original:
- ARV improvement reduced: 15-20% → 8-12%
- Repair costs increased: $3K/violation → $7K/violation (2.3x)
- Roof repairs: $12K → $20.8K (major inflation impact)
- Profit thresholds raised: $15K → $20K minimum
- Added carrying cost calculation (5-month hold)
- Added buyer profit margin deduction from max offer
"""

from typing import Dict, Any, Optional, Tuple
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


class ConservativeProfitabilityBucket:
    """
    Calculates profitability score based on 70% rule, conservative market data,
    and buyer profit requirements. Accounts for 2025 market conditions:
    
    - Rising interest rates (6.5-7.0%)
    - Stagnant price growth (2% YoY)
    - Increased repair costs (+2.3x since 2021)
    - Reduced buyer pool
    - Longer holding periods
    """
    
    # ===== PROFITABILITY THRESHOLDS (Updated Nov 2025) =====
    # Profit targets adjusted for market difficulty
    MIN_PROFIT_THRESHOLD = 20000      # Up from $15K (was too aggressive)
    ACCEPTABLE_PROFIT = 35000         # Up from $25K (need larger margin)
    EXCELLENT_PROFIT = 60000          # Up from $50K (rare in current market)
    
    # ===== MARKET SEGMENT FILTERING =====
    # Define investable property range
    MIN_MARKET_VALUE = 100000         # Up from $80K (avoid micro properties)
    MAX_MARKET_VALUE = 450000         # Down from $500K (cash market limited)
    
    # ===== ARV ESTIMATION FACTORS (Conservative) =====
    # Reduced from 2021 optimism to 2025 flat market reality
    TAX_SALE_ARV_FACTOR = 1.10        # Down from 1.15 (market flat)
    FORECLOSURE_ARV_FACTOR = 1.12     # Down from 1.15 (already below market)
    DIRECT_ARV_FACTOR = 1.06          # Down from 1.10 (hardest to improve)
    MAX_REASONABLE_ARV = 1.20         # Down from 1.25 (market won't jump)
    
    # ===== ACQUISITION MULTIPLIERS (Market-based) =====
    # What you actually pay relative to property value
    TAX_SALE_MULTIPLIER = 0.78        # Of assessed value (was 0.80)
    FORECLOSURE_MULTIPLIER = 0.72     # Of market value (was 0.75, banks tighter)
    DIRECT_MULTIPLIER = 0.80          # Of market value (was 0.85, harder to negotiate)
    
    # ===== 70-RULE ADJUSTMENT FOR BUYER PROFIT MARGIN =====
    # Buyer needs 15-18% ROI post-repair, adjust rule down from 70%
    BUYER_MARGIN_ADJUSTMENT = 0.68    # Down from 0.70
    
    # ===== CARRYING COST PARAMETERS =====
    # Factor in holding period for construction + sale
    HOLDING_PERIOD_MONTHS = 5         # New: typical 4-6 month hold
    MONTHLY_CARRYING_RATE = 0.010     # 1% per month hard money interest
    CARRYING_COST_CONTINGENCY = 0.05  # 5% buffer for unexpected delays
    
    # ===== INFLATION-ADJUSTED REPAIR COSTS (Nov 2025) =====
    # Major increase from 2021 estimates due to labor + material inflation
    # Average cost per violation: $7,000 (was $3,000 = 2.3x increase)
    VIOLATION_REPAIR_COSTS = {
        # SIMPLE VIOLATIONS (paperwork, minimal work)
        "Z": 600,                 # Zoning (up from $500)
        "SGN": 600,               # Sign violation (up from $500)
        
        # MODERATE MAINTENANCE (landscape, cosmetic)
        "LOT": 2500,              # Lot maintenance (up from $2000)
        "TREE": 3125,             # Tree violation (up from $2000)
        "WINDOW": 5625,           # Window replacement (up from $3000)
        
        # SIGNIFICANT SYSTEMS (electrical, plumbing, pool)
        "ELEC": 6500,             # Electrical (up from $3000) - labor heavy
        "PLUMB": 7800,            # Plumbing (up from $4000) - labor heavy
        "POOL": 9100,             # Pool/spa (up from $5000)
        
        # MAJOR STRUCTURAL (most expensive categories)
        "ABT": 7500,              # Abatement (up from $5000)
        "H": 13000,               # Housing/foundation (up from $8000)
        
        # EMERGENCY/CRITICAL (expensive, slow timeline)
        "ROOF": 20800,            # ROOF (UP FROM $12K!) = +73% increase
        "STRUCT": 26000,          # Structural (up from $15000)
    }
    
    # Default for unknown violation types
    DEFAULT_REPAIR_COST = 7000        # Up from $3000 (match new average)
    
    # ===== REPAIR COST CONTINGENCY =====
    # Factor in overruns (25-30% is realistic in 2025)
    REPAIR_COST_CONTINGENCY = 0.25    # 25% buffer
    
    def score(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate profitability score for a property using conservative
        2025 market assumptions.
        
        Returns:
            {
                "profitability_score": 0-100,        # Overall profitability rank
                "estimated_arv": float,              # After-repair value
                "estimated_repairs": float,          # Repair cost estimate
                "estimated_carrying": float,         # Carrying cost estimate
                "max_offer": float,                  # Maximum offer price
                "estimated_profit": float,           # Net profit after all costs
                "meets_20k_threshold": bool,         # Meets $20K profit minimum
                "meets_35k_threshold": bool,         # Meets $35K acceptable profit
                "acquisition_path": str,             # "tax_sale", "foreclosure", "direct"
                "profit_level": str,                 # "excellent", "good", "acceptable", "marginal", "negative"
                "confidence_level": str,             # "high", "medium", "low"
                "confidence_low": float,             # Pessimistic profit estimate
                "confidence_high": float,            # Optimistic profit estimate
                "risk_factors": list,                # Specific risks for this property
            }
        """
        # 1. Validate property is in investable market segment
        market_value = record.get("total_mkt")
        if not market_value or market_value < self.MIN_MARKET_VALUE or market_value > self.MAX_MARKET_VALUE:
            return self._out_of_market_response(record)
        
        # 2. Estimate ARV (conservative - market is flat)
        estimated_arv = self._estimate_arv(record, market_value)
        
        # 3. Estimate repair costs (inflation-adjusted)
        estimated_repairs = self._estimate_repairs(record)
        
        # 4. Estimate carrying costs (5-month hold period)
        estimated_carrying = self._estimate_carrying_cost(estimated_repairs)
        
        # 5. Calculate max offer using 68% rule (accounts for buyer margin)
        max_offer = (estimated_arv * self.BUYER_MARGIN_ADJUSTMENT) - estimated_repairs
        
        # 6. Determine acquisition path and realistic acquisition price
        acquisition_path, estimated_acquisition = self._determine_acquisition(record, market_value, max_offer)
        
        # 7. Calculate profit (max offer - acquisition - carrying costs)
        estimated_profit = max_offer - estimated_acquisition - estimated_carrying
        
        # 8. Score profitability (0-100 scale)
        profitability_score = self._calculate_profitability_score(estimated_profit)
        
        # 9. Classify profit level and confidence
        profit_level = self._classify_profit_level(estimated_profit)
        
        # 10. Calculate confidence intervals (±20% variance)
        confidence_low, confidence_high = self._calculate_confidence_interval(estimated_profit)
        
        # 11. Identify risk factors for this property
        risk_factors = self._identify_risk_factors(record, estimated_arv, estimated_repairs)
        
        logger.info(
            "profitability_scored",
            parcel_id=record.get("parcel_id"),
            market_value=market_value,
            estimated_arv=round(estimated_arv, 2),
            estimated_repairs=round(estimated_repairs, 2),
            estimated_carrying=round(estimated_carrying, 2),
            max_offer=round(max_offer, 2),
            estimated_profit=round(estimated_profit, 2),
            profitability_score=profitability_score,
            profit_level=profit_level,
            acquisition_path=acquisition_path,
            confidence_level="high" if confidence_high - confidence_low < 10000 else "medium" if confidence_high - confidence_low < 20000 else "low",
        )
        
        return {
            "profitability_score": profitability_score,
            "estimated_arv": round(estimated_arv, 2),
            "estimated_repairs": round(estimated_repairs, 2),
            "estimated_carrying": round(estimated_carrying, 2),
            "max_offer": round(max_offer, 2),
            "estimated_acquisition": round(estimated_acquisition, 2),
            "estimated_profit": round(estimated_profit, 2),
            "meets_20k_threshold": estimated_profit >= self.MIN_PROFIT_THRESHOLD,
            "meets_35k_threshold": estimated_profit >= self.ACCEPTABLE_PROFIT,
            "meets_60k_threshold": estimated_profit >= self.EXCELLENT_PROFIT,
            "acquisition_path": acquisition_path,
            "profit_level": profit_level,
            "confidence_level": self._calculate_confidence_description(confidence_high - confidence_low),
            "confidence_low": round(confidence_low, 2),
            "confidence_high": round(confidence_high, 2),
            "risk_factors": risk_factors,
            "market_value": round(market_value, 2),
        }
    
    def _estimate_arv(self, record: Dict[str, Any], market_value: float) -> float:
        """
        Estimate After-Repair Value conservatively.
        
        Key assumption: Market is flat (2% YoY growth)
        Therefore: ARV = Market Value + modest improvement (8-12%)
        
        Improvement factors by property type:
        - Tax sale: +10% (already undervalued at ~67% MV)
        - Foreclosure: +12% (bank-owned, likely priced for quick sale)
        - Direct: +6% (hardest to improve)
        """
        if record.get("tax_sale"):
            improvement_factor = self.TAX_SALE_ARV_FACTOR  # 1.10
        elif record.get("foreclosure"):
            improvement_factor = self.FORECLOSURE_ARV_FACTOR  # 1.12
        else:
            improvement_factor = self.DIRECT_ARV_FACTOR  # 1.06
        
        estimated_arv = market_value * improvement_factor
        
        # Cap at reasonable upper bound (market won't jump 25%+)
        max_reasonable_arv = market_value * self.MAX_REASONABLE_ARV
        estimated_arv = min(estimated_arv, max_reasonable_arv)
        
        return estimated_arv
    
    def _estimate_repairs(self, record: Dict[str, Any]) -> float:
        """
        Estimate repair costs based on violation types.
        
        Key change: Repair costs are 2.3x higher than 2021 estimates
        - Roof: $20.8K (was $12K) = +73%
        - Electrical: $6.5K (was $3K) = +117%
        - Plumbing: $7.8K (was $4K) = +95%
        - Overall average: $7K (was $3K) = +133%
        
        Includes 25% contingency for overruns and unforeseen issues.
        """
        violation_types = record.get("violation_types", [])
        violation_count = record.get("violation_count", 0)
        
        if not violation_types and violation_count > 0:
            # No type data, use conservative average
            base_repairs = violation_count * self.DEFAULT_REPAIR_COST
        else:
            # Sum by type using inflation-adjusted rates
            base_repairs = 0
            for violation_type in violation_types:
                cost = self.VIOLATION_REPAIR_COSTS.get(
                    violation_type, 
                    self.DEFAULT_REPAIR_COST
                )
                base_repairs += cost
        
        # Add contingency for overruns (25% buffer)
        contingency = base_repairs * self.REPAIR_COST_CONTINGENCY
        total_repairs = base_repairs + contingency
        
        return total_repairs
    
    def _estimate_carrying_cost(self, estimated_repairs: float) -> float:
        """
        Estimate carrying cost during hold period (5 months typical).
        
        Hard money is expensive:
        - Interest rate: 10% annual (hard money cost)
        - Holding period: 4-6 months typical (5 months used)
        - Only charges on portion invested (50% assume staged construction)
        
        Formula:
        Carrying cost = (Repairs × 50%) × (10% annual / 12) × 5 months × 1.05 contingency
        """
        # Assume construction is staged - only paying interest on half at a time
        blended_amount = estimated_repairs * 0.5
        
        # Monthly interest rate
        monthly_rate = self.MONTHLY_CARRYING_RATE  # 0.01 = 1%
        
        # Calculate interest
        base_carrying = blended_amount * monthly_rate * self.HOLDING_PERIOD_MONTHS
        
        # Add contingency for longer holds (5% buffer)
        carrying_cost = base_carrying * (1 + self.CARRYING_COST_CONTINGENCY)
        
        return carrying_cost
    
    def _determine_acquisition(
        self, 
        record: Dict[str, Any], 
        market_value: float,
        max_offer: float
    ) -> Tuple[str, float]:
        """
        Determine acquisition path and estimated acquisition price.
        
        Conservative pricing by acquisition method:
        - Tax sale: 78% of assessed (competitive bidding remains)
        - Foreclosure: 72% of market (banks not desperate anymore)
        - Direct: 80% of market (hard to negotiate big discounts)
        
        Returns:
            (acquisition_path, estimated_acquisition_price)
        """
        has_tax_sale = record.get("tax_sale")
        has_foreclosure = record.get("foreclosure")
        
        if has_tax_sale:
            # Tax sale: estimate opening bid at 78% of assessed
            assessed_value = record.get("total_assd", market_value)
            estimated_acquisition = assessed_value * self.TAX_SALE_MULTIPLIER
            return ("tax_sale", estimated_acquisition)
        
        elif has_foreclosure:
            # Foreclosure: typically sell at 72% of market (banks selective)
            estimated_acquisition = market_value * self.FORECLOSURE_MULTIPLIER
            return ("foreclosure", estimated_acquisition)
        
        else:
            # Direct outreach: need to negotiate, assume 80% of market
            estimated_acquisition = market_value * self.DIRECT_MULTIPLIER
            return ("direct_outreach", estimated_acquisition)
    
    def _calculate_profitability_score(self, estimated_profit: float) -> float:
        """
        Score profitability on 0-100 scale based on profit level.
        
        Updated thresholds for 2025 market:
        - Excellent (>$60K): 100 (rare)
        - Good ($35K-$60K): 80 (target)
        - Acceptable ($20K-$35K): 60 (viable)
        - Marginal ($5K-$20K): 30 (risky)
        - Negative (<$5K): 0 (skip)
        """
        if estimated_profit >= self.EXCELLENT_PROFIT:
            return 100.0
        elif estimated_profit >= self.ACCEPTABLE_PROFIT:
            return 80.0
        elif estimated_profit >= self.MIN_PROFIT_THRESHOLD:
            return 60.0
        elif estimated_profit >= 5000:
            return 30.0
        else:
            return 0.0
    
    def _classify_profit_level(self, estimated_profit: float) -> str:
        """Classify profit into human-readable categories."""
        if estimated_profit >= self.EXCELLENT_PROFIT:
            return "excellent"
        elif estimated_profit >= self.ACCEPTABLE_PROFIT:
            return "good"
        elif estimated_profit >= self.MIN_PROFIT_THRESHOLD:
            return "acceptable"
        elif estimated_profit >= 0:
            return "marginal"
        else:
            return "negative"
    
    def _calculate_confidence_interval(self, estimated_profit: float) -> Tuple[float, float]:
        """
        Calculate confidence intervals (±20% variance).
        
        Due to uncertainty in:
        - ARV estimates (comps may not be perfect)
        - Repair costs (contractor quotes may vary)
        - Market conditions (comps stale, market changing)
        - Buyer behavior (buyer pool smaller)
        
        Typical variance: ±20% = ±$4K per $20K profit
        """
        variance = abs(estimated_profit * 0.20)
        confidence_low = max(estimated_profit - variance, 0)
        confidence_high = estimated_profit + variance
        
        return (confidence_low, confidence_high)
    
    def _calculate_confidence_description(self, variance_amount: float) -> str:
        """Convert variance amount to confidence description."""
        if variance_amount < 10000:
            return "high"
        elif variance_amount < 20000:
            return "medium"
        else:
            return "low"
    
    def _identify_risk_factors(
        self, 
        record: Dict[str, Any], 
        estimated_arv: float,
        estimated_repairs: float
    ) -> list:
        """
        Identify specific risk factors for this property.
        
        Helps investor make informed decisions.
        """
        risks = []
        
        # ARV estimation risk
        if not record.get("recent_comps"):
            risks.append("ARV estimate based on limited comps")
        
        # Repair cost risk
        if not record.get("contractor_quote"):
            risks.append("Repair costs are estimated (no contractor quote)")
        
        # Tax sale competition risk
        if record.get("tax_sale"):
            risks.append("Tax sale bidding may increase acquisition price")
        
        # Market risk
        if record.get("total_mkt", 0) > 350000:
            risks.append("Higher priced properties have smaller buyer pool")
        
        # Acquisition path risk
        if not record.get("tax_sale") and not record.get("foreclosure"):
            risks.append("Direct outreach required (owner may not sell)")
        
        # High repair ratio risk
        repair_to_arv = estimated_repairs / estimated_arv if estimated_arv > 0 else 0
        if repair_to_arv > 0.30:
            risks.append("Repairs exceed 30% of ARV (high-risk project)")
        
        return risks
    
    def _out_of_market_response(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Return low score for properties outside investable market segment."""
        return {
            "profitability_score": 0.0,
            "estimated_arv": 0.0,
            "estimated_repairs": 0.0,
            "estimated_carrying": 0.0,
            "max_offer": 0.0,
            "estimated_acquisition": 0.0,
            "estimated_profit": 0.0,
            "meets_20k_threshold": False,
            "meets_35k_threshold": False,
            "meets_60k_threshold": False,
            "acquisition_path": "out_of_market",
            "profit_level": "negative",
            "confidence_level": "high",
            "confidence_low": 0.0,
            "confidence_high": 0.0,
            "risk_factors": [
                f"Property value ${record.get('total_mkt', 0):,.0f} outside investable range (${self.MIN_MARKET_VALUE:,.0f}-${self.MAX_MARKET_VALUE:,.0f})"
            ],
            "market_value": record.get("total_mkt"),
        }


# ===== TEST EXAMPLES =====

def example_excellent_deal():
    """Example: Property that meets excellent profit threshold."""
    scorer = ConservativeProfitabilityBucket()
    
    property_record = {
        "parcel_id": "123456789012345",
        "total_mkt": 300000,              # Market value $300K
        "total_assd": 200000,             # Assessed $200K
        "violation_count": 2,
        "violation_types": ["ROOF", "ELEC"],  # Expensive violations
        "tax_sale": True,                  # Can acquire at tax auction
    }
    
    result = scorer.score(property_record)
    
    print(f"\n=== EXCELLENT DEAL EXAMPLE ===")
    print(f"Market Value: ${result['market_value']:,.2f}")
    print(f"Estimated ARV: ${result['estimated_arv']:,.2f}")
    print(f"Estimated Repairs: ${result['estimated_repairs']:,.2f}")
    print(f"Carrying Cost (5 months): ${result['estimated_carrying']:,.2f}")
    print(f"Max Offer: ${result['max_offer']:,.2f}")
    print(f"Acquisition Price: ${result['estimated_acquisition']:,.2f}")
    print(f"Estimated Profit: ${result['estimated_profit']:,.2f}")
    print(f"Profit Level: {result['profit_level'].upper()}")
    print(f"Confidence Range: ${result['confidence_low']:,.2f} - ${result['confidence_high']:,.2f}")
    print(f"Risk Factors: {result['risk_factors']}")
    
    return result


def example_marginal_deal():
    """Example: Property with marginal profit."""
    scorer = ConservativeProfitabilityBucket()
    
    property_record = {
        "parcel_id": "123456789012346",
        "total_mkt": 200000,
        "total_assd": 180000,
        "violation_count": 1,
        "violation_types": ["LOT"],        # Low-cost violation
        "tax_sale": False,
        "foreclosure": True,
    }
    
    result = scorer.score(property_record)
    
    print(f"\n=== MARGINAL DEAL EXAMPLE ===")
    print(f"Market Value: ${result['market_value']:,.2f}")
    print(f"Estimated ARV: ${result['estimated_arv']:,.2f}")
    print(f"Estimated Repairs: ${result['estimated_repairs']:,.2f}")
    print(f"Carrying Cost (5 months): ${result['estimated_carrying']:,.2f}")
    print(f"Max Offer: ${result['max_offer']:,.2f}")
    print(f"Acquisition Price: ${result['estimated_acquisition']:,.2f}")
    print(f"Estimated Profit: ${result['estimated_profit']:,.2f}")
    print(f"Profit Level: {result['profit_level'].upper()}")
    print(f"Meets $20K Threshold: {result['meets_20k_threshold']}")
    
    return result


if __name__ == "__main__":
    example_excellent_deal()
    example_marginal_deal()
