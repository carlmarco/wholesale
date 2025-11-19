# Implementation Roadmap: Lead Quality Improvements

**Created**: November 15, 2025  
**Status**: READY FOR EXECUTION  
**Overall Timeline**: 6-8 weeks (Phase 3.5 → 3.6 → Phase 4)

---

## Phase Overview

```
CURRENT STATE (Phase 3.5)          NEAR TERM (Phase 3.6)           MEDIUM TERM (Phase 4)
┌─────────────────────────┐        ┌──────────────────────┐         ┌────────────────────┐
│  Distress identification │        │  Profit validation   │         │  Contact enrichment│
│  ✓ Ingestion working    │        │  Better ARV/repairs  │         │  (Skip tracing)    │
│  ✗ Profit math missing  │        │  Proper equity calc  │         │  + Outreach ready  │
│  ✗ No contact info      │        │  Filter by market val│         │                    │
│  ✗ No ARV/repairs       │        │  Result: 60-70% qual │         │  Result: 100% qual │
└─────────────────────────┘        └──────────────────────┘         │  (with outreach)   │
         Nov 2025                    Dec 2025 - Jan 2026              │  (Jan-Feb 2026)    │
      (current state)                  (1-2 months)                   │  (2-3 months)      │
                                                                      └────────────────────┘
```

---

## PHASE 3.6: PROFIT VALIDATION & LEAD QUALITY (1-2 months)

### Sprint 3.6.1: Add Profitability Bucket to Scoring (Week 1-2)

**Objective**: Implement 4-bucket scoring with profitability validation

#### Task 3.6.1.1: Create new `ProfitabilityScorer` class

**File**: `src/wholesaler/scoring/profitability.py` (NEW)

```python
"""
Profitability validation for wholesale deals.

Implements 70% rule and profit threshold analysis.
"""
from typing import Dict, Any, Optional, Tuple
from src.wholesaler.utils.logger import get_logger

logger = get_logger(__name__)


class ProfitabilityBucket:
    """Calculates profitability score based on 70% rule and profit thresholds."""
    
    # Constants
    MIN_PROFIT_THRESHOLD = 15000  # Minimum acceptable profit
    ACCEPTABLE_PROFIT = 25000     # Good profit
    EXCELLENT_PROFIT = 50000      # Excellent profit
    
    # Market segment
    MIN_MARKET_VALUE = 80000      # Don't waste time on very small properties
    MAX_MARKET_VALUE = 500000     # Market segment focus
    
    # Repair cost multipliers by violation type
    VIOLATION_REPAIR_COSTS = {
        "Z": 500,           # Zoning (paperwork)
        "LOT": 2000,        # Lot maintenance/landscaping
        "H": 8000,          # Housing/structural (average)
        "SGN": 500,         # Sign violation
        "ABT": 5000,        # Abatement
        "TREE": 2000,       # Tree violation
        "POOL": 5000,       # Pool/spa
        "ELEC": 3000,       # Electrical
        "PLUMB": 4000,      # Plumbing
        "ROOF": 12000,      # Roof damage
        "WINDOW": 3000,     # Window damage
        "STRUCT": 15000,    # Structural issues
    }
    
    def score(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate profitability score for a property.
        
        Returns:
            {
                "profitability_score": 0-100,
                "estimated_arv": float,
                "estimated_repairs": float,
                "max_offer": float,
                "estimated_profit": float,
                "meets_70_rule": bool,
                "acquisition_path": str,  # "tax_sale", "foreclosure", "direct", "unknown"
                "profit_level": str,  # "excellent", "good", "acceptable", "marginal", "negative"
            }
        """
        # 1. Validate property is in investable market segment
        market_value = record.get("total_mkt")
        if not market_value or market_value < self.MIN_MARKET_VALUE or market_value > self.MAX_MARKET_VALUE:
            return self._out_of_market_response(record)
        
        # 2. Estimate ARV (conservative - use market value as baseline)
        estimated_arv = self._estimate_arv(record, market_value)
        
        # 3. Estimate repair costs
        estimated_repairs = self._estimate_repairs(record)
        
        # 4. Calculate max offer using 70% rule
        max_offer = (estimated_arv * 0.70) - estimated_repairs
        
        # 5. Determine acquisition path and realistic acquisition price
        acquisition_path, estimated_acquisition = self._determine_acquisition(record, max_offer)
        
        # 6. Calculate profit
        estimated_profit = max_offer - estimated_acquisition
        
        # 7. Score profitability
        profitability_score = self._calculate_profitability_score(estimated_profit)
        
        # 8. Classify profit level
        profit_level = self._classify_profit_level(estimated_profit)
        
        logger.info(
            "profitability_scored",
            parcel_id=record.get("parcel_id"),
            market_value=market_value,
            estimated_arv=estimated_arv,
            estimated_repairs=estimated_repairs,
            max_offer=max_offer,
            estimated_profit=estimated_profit,
            profitability_score=profitability_score,
            acquisition_path=acquisition_path,
        )
        
        return {
            "profitability_score": profitability_score,
            "estimated_arv": round(estimated_arv, 2),
            "estimated_repairs": round(estimated_repairs, 2),
            "max_offer": round(max_offer, 2),
            "estimated_profit": round(estimated_profit, 2),
            "meets_70_rule": estimated_profit >= self.MIN_PROFIT_THRESHOLD,
            "acquisition_path": acquisition_path,
            "profit_level": profit_level,
            "market_value": market_value,
        }
    
    def _estimate_arv(self, record: Dict[str, Any], market_value: float) -> float:
        """
        Estimate After-Repair Value conservatively.
        
        Conservative approach: Use market value + 5-10% improvement
        Better approach (future): Use comp analysis
        """
        # For now, use market value as floor and assume 10% improvement
        # In Phase 3.6.2 (comp analysis), this will be replaced with real comps
        
        # If property is in foreclosure/tax sale, market value likely depressed
        # So apply small improvement factor
        if record.get("foreclosure") or record.get("tax_sale"):
            improvement_factor = 1.15  # 15% improvement (assuming below-market acquisition)
        else:
            improvement_factor = 1.10  # 10% improvement (conservative)
        
        estimated_arv = market_value * improvement_factor
        
        # Cap at reasonable upper bound (don't assume crazy improvements)
        max_reasonable_arv = market_value * 1.25  # 25% max improvement
        estimated_arv = min(estimated_arv, max_reasonable_arv)
        
        return estimated_arv
    
    def _estimate_repairs(self, record: Dict[str, Any]) -> float:
        """
        Estimate repair costs based on violation types.
        
        Sum repair costs by violation type + 20% contingency.
        """
        violation_types = record.get("violation_types", [])
        violation_count = record.get("violation_count", 0)
        
        if not violation_types and violation_count > 0:
            # No type data, use average estimate
            avg_repair_per_violation = 3000
            estimated_repairs = violation_count * avg_repair_per_violation
        else:
            # Sum by type
            estimated_repairs = 0
            for violation_type in violation_types:
                estimated_repairs += self.VIOLATION_REPAIR_COSTS.get(violation_type, 3000)
        
        # Add contingency (20% for unexpected issues)
        contingency = estimated_repairs * 0.20
        total_repairs = estimated_repairs + contingency
        
        return total_repairs
    
    def _determine_acquisition(self, record: Dict[str, Any], max_offer: float) -> Tuple[str, float]:
        """
        Determine acquisition path and estimated acquisition price.
        
        Returns:
            (acquisition_path, estimated_acquisition_price)
        """
        has_tax_sale = record.get("tax_sale")
        has_foreclosure = record.get("foreclosure")
        market_value = record.get("total_mkt", 0)
        
        if has_tax_sale:
            # Tax sale: estimate opening bid at 70-80% of assessed value
            # Usually opens below market, but competitive bidding brings up price
            assessed_value = record.get("total_assd", market_value)
            opening_bid_estimate = assessed_value * 0.75
            
            # Final acquisition likely higher due to bidding
            # Conservative: assume win at 80% of max_offer
            estimated_acquisition = max_offer * 0.80
            
            return ("tax_sale", estimated_acquisition)
        
        elif has_foreclosure:
            # Foreclosure: typically sell at 60-75% of judgment/market
            judgment = record.get("judgment_amount", market_value)
            estimated_acquisition = judgment * 0.70
            
            return ("foreclosure", estimated_acquisition)
        
        else:
            # Direct outreach to owner: need massive discount to buy
            # Realistic: owner won't sell at max_offer without extreme distress
            # Assume we negotiate to 85% of max_offer (worst case: no deal)
            estimated_acquisition = max_offer * 0.85
            
            return ("direct_outreach", estimated_acquisition)
    
    def _calculate_profitability_score(self, estimated_profit: float) -> float:
        """
        Score profitability on 0-100 scale.
        
        Excellent (>$50K): 100
        Good ($25K-$50K): 80
        Acceptable ($15K-$25K): 60
        Marginal ($5K-$15K): 30
        Negative (<$5K): 0
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
    
    def _out_of_market_response(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Return low score for properties outside investable market."""
        return {
            "profitability_score": 0.0,
            "estimated_arv": 0.0,
            "estimated_repairs": 0.0,
            "max_offer": 0.0,
            "estimated_profit": 0.0,
            "meets_70_rule": False,
            "acquisition_path": "out_of_market",
            "profit_level": "negative",
            "market_value": record.get("total_mkt"),
        }
```

**Testing**: `tests/wholesaler/scoring/test_profitability.py` (NEW)

```python
"""Tests for profitability scoring."""
import pytest
from src.wholesaler.scoring.profitability import ProfitabilityBucket


@pytest.mark.unit
class TestProfitabilityBucket:
    
    def test_excellent_deal(self):
        """Test excellent profit scenario."""
        scorer = ProfitabilityBucket()
        record = {
            "parcel_id": "123456789012345",
            "total_mkt": 300000,          # Market value $300K
            "total_assd": 100000,         # Assessed $100K (old assessment)
            "violation_count": 3,
            "violation_types": ["ELEC", "ROOF"],
            "tax_sale": True,             # Can acquire via tax sale
        }
        
        result = scorer.score(record)
        
        # Expected:
        # ARV: $300K * 1.15 = $345K
        # Repairs: $3K + $12K + contingency = $18K
        # Max offer: ($345K * 0.70) - $18K = $223.5K
        # Acquisition (tax sale, 80% of max): $178.8K
        # Profit: $223.5K - $178.8K = $44.7K
        # Profit level: "good"
        
        assert result["profitability_score"] == 80.0
        assert result["profit_level"] == "good"
        assert result["meets_70_rule"] is True
        assert result["acquisition_path"] == "tax_sale"
        assert result["estimated_profit"] > 40000
    
    def test_marginal_deal(self):
        """Test marginal profit scenario."""
        scorer = ProfitabilityBucket()
        record = {
            "parcel_id": "123456789012346",
            "total_mkt": 150000,
            "total_assd": 120000,
            "violation_count": 2,
            "violation_types": ["LOT"],
            "tax_sale": False,
            "foreclosure": False,
        }
        
        result = scorer.score(record)
        
        # Expected:
        # ARV: $150K * 1.10 = $165K
        # Repairs: $2K + contingency = $2.4K
        # Max offer: ($165K * 0.70) - $2.4K = $113.1K
        # Acquisition (direct, 85% of max): $96.1K
        # Profit: $113.1K - $96.1K = $17K
        # Profit level: "acceptable"
        
        assert result["profitability_score"] == 60.0
        assert result["profit_level"] == "acceptable"
        assert result["meets_70_rule"] is True
    
    def test_out_of_market(self):
        """Test property outside investable range."""
        scorer = ProfitabilityBucket()
        record = {
            "parcel_id": "123456789012347",
            "total_mkt": 600000,  # Too expensive
            "violation_count": 0,
        }
        
        result = scorer.score(record)
        
        assert result["profitability_score"] == 0.0
        assert result["profit_level"] == "negative"
        assert result["acquisition_path"] == "out_of_market"
        assert result["meets_70_rule"] is False
```

**Effort**: 3-4 hours

---

#### Task 3.6.1.2: Integrate profitability bucket into HybridBucketScorer

**File**: `src/wholesaler/scoring/scorers.py` (MODIFY)

Replace the old 3-bucket model with new 4-bucket model:

```python
# OLD (3 buckets):
WEIGHTS = {"distress": 0.65, "disposition": 0.20, "equity": 0.15}

# NEW (4 buckets):
WEIGHTS = {
    "distress": 0.50,         # Down from 0.65
    "disposition": 0.20,      # Same
    "equity": 0.10,           # Down from 0.15
    "profitability": 0.20,    # NEW!
}
```

Update `HybridBucketScorer._tier()` to require profitability for high tiers:

```python
def score(self, record: Dict[str, Any]) -> Dict[str, Any]:
    """Score with profit validation."""
    from src.wholesaler.scoring.profitability import ProfitabilityBucket
    
    buckets = self._bucket_scores(record)
    
    # Calculate profitability
    profit_bucket = ProfitabilityBucket()
    profit_result = profit_bucket.score(record)
    profit_score = profit_result["profitability_score"]
    
    # Weighted total (4 buckets now)
    total = (
        buckets.distress * self.WEIGHTS["distress"] +
        buckets.disposition * self.WEIGHTS["disposition"] +
        buckets.equity * self.WEIGHTS["equity"] +
        profit_score * self.WEIGHTS["profitability"]
    )
    
    # Apply bonuses (keep existing logic)
    if record.get("tax_sale"):
        total += 15
    if record.get("foreclosure"):
        total += 10
    
    total = _clamp(total)
    tier = self._tier(total, profit_result)  # Pass profit result for validation
    
    return {
        "total_score": total,
        "tier": tier,
        "bucket_scores": buckets,
        "profitability": profit_result,  # NEW: Add profitability details
    }

@staticmethod
def _tier(score: float, profit_result: Dict) -> str:
    """
    Assign tier with profit validation.
    
    NEW LOGIC: High tiers require profit validation
    """
    # For Tier A/B, require profitability score > 0
    if score >= 65 and profit_result["profitability_score"] > 0:
        return "A"
    if score >= 50 and profit_result["profitability_score"] > 0:
        return "B"
    if score >= 40:
        return "C"
    return "D"
```

**Effort**: 2-3 hours

---

#### Task 3.6.1.3: Add tests and validation

**File**: `tests/wholesaler/scoring/test_scorers.py` (MODIFY)

Add tests for new 4-bucket scoring:

```python
@pytest.mark.unit
def test_hybrid_scorer_with_profitability():
    """Test that profitable deals get higher tiers."""
    scorer = HybridBucketScorer()
    
    # Good deal: tax sale, high violations, should be Tier A
    good_deal = {
        "parcel_id": "123",
        "violation_count": 5,
        "open_violations": 1,
        "most_recent_violation": "2025-11-01",
        "total_mkt": 250000,
        "total_assd": 100000,
        "tax_sale": True,
        "violation_types": ["ELEC"],
    }
    
    result = scorer.score(good_deal)
    
    assert result["tier"] == "A"
    assert result["profitability"]["meets_70_rule"] is True
    assert result["profitability"]["profit_level"] in ["good", "acceptable"]


@pytest.mark.unit
def test_hybrid_scorer_rejects_unprofitable():
    """Test that unprofitable deals get downgraded."""
    scorer = HybridBucketScorer()
    
    # Bad deal: high violations but huge market value (outside range)
    bad_deal = {
        "parcel_id": "124",
        "violation_count": 10,
        "open_violations": 5,
        "most_recent_violation": "2025-11-01",
        "total_mkt": 600000,  # Too expensive
        "total_assd": 500000,
        "tax_sale": False,
        "violation_types": ["H", "ROOF"],
    }
    
    result = scorer.score(bad_deal)
    
    assert result["tier"] in ["C", "D"]
    assert result["profitability"]["meets_70_rule"] is False
```

**Effort**: 1-2 hours

**Total for Task 3.6.1: 6-9 hours**

---

### Sprint 3.6.2: Fix Equity Calculation (Week 1)

**Objective**: Replace meaningless equity% with realistic measure

#### Task 3.6.2.1: Correct equity bucket logic

**File**: `src/wholesaler/scoring/scorers.py` (MODIFY)

Current broken equity calculation:
```python
equity_pct = property_record.get("equity_percent") or record.get("equity_percent")
# This is calculated as: market_value / assessed_value × 100
# Which is WRONG - it's not equity, it's a tax assessment ratio
```

New approach (without loan data):
```python
def _equity_bucket(self, record: Dict[str, Any]) -> float:
    """
    Calculate equity proxy score.
    
    NOTE: Real equity = (market_value - loan_balance) / market_value
    We don't have loan balance, so we use market vs assessed as proxy.
    
    A high market-to-assessed ratio suggests:
    - Property may be tax-advantaged (not equity)
    - OR property has appreciated significantly (could indicate equity)
    
    This bucket should be DE-EMPHASIZED until loan data available.
    Currently weighted at only 10% (down from 15%).
    """
    market_value = record.get("total_mkt", 0)
    assessed_value = record.get("total_assd", 0)
    
    if not market_value or not assessed_value or assessed_value == 0:
        return 0.0
    
    # Market-to-assessed ratio (proxy only)
    ratio = market_value / assessed_value
    
    # Score: Higher ratio = potentially more equity
    # But also could just mean old tax assessment
    # Therefore, cap the scoring at 30 (modest weight)
    equity_score = min(30.0, ratio * 10)
    
    return equity_score
```

**Document the limitation**:

```python
# Add to class docstring
"""
KNOWN LIMITATION: Equity bucket uses market/assessed ratio as proxy.

This is NOT real equity calculation (which requires loan balance data).
Limitations:
- High ratio could mean old tax assessment, not actual seller equity
- Without loan balance, we can't validate true equity position
- Results in false positives (properties that look good but have high mortgages)

FUTURE IMPROVEMENT (Phase 4+):
- Integrate with MLS data (which includes loan info)
- Or require manual contact to confirm equity position
- Meanwhile: Use this as weak signal only (10% weight)
"""
```

**Effort**: 1-2 hours

---

### Sprint 3.6.3: Repair Costs by Violation Type (Week 1)

**Objective**: Replace violation_count × multiplier with type-specific costs

#### Task 3.6.3.1: Create violation repair cost mapping

**File**: `src/wholesaler/scoring/violation_costs.py` (NEW)

```python
"""
Repair cost estimates by code violation type.

Based on typical Orlando market repair costs.
Should be updated quarterly based on actual job quotes.
"""

# Violation code → typical repair cost
VIOLATION_REPAIR_MATRIX = {
    # Administrative/Zoning
    "Z": {
        "description": "Zoning violation",
        "cost_low": 200,
        "cost_high": 1000,
        "avg": 500,
        "notes": "Often administrative; may just need paperwork"
    },
    
    # Lot/Landscaping
    "LOT": {
        "description": "Lot maintenance, landscaping",
        "cost_low": 1000,
        "cost_high": 3000,
        "avg": 2000,
        "notes": "Clearing weeds, mowing, debris removal"
    },
    
    # Housing/Structural (average)
    "H": {
        "description": "Housing code violation (average)",
        "cost_low": 5000,
        "cost_high": 15000,
        "avg": 8000,
        "notes": "Wide range depending on specific issue"
    },
    
    # Sign violations
    "SGN": {
        "description": "Sign violation",
        "cost_low": 300,
        "cost_high": 1000,
        "avg": 500,
        "notes": "Remove/replace signage"
    },
    
    # Abatement
    "ABT": {
        "description": "Abatement (animal, nuisance)",
        "cost_low": 2000,
        "cost_high": 8000,
        "avg": 5000,
        "notes": "Animal removal, nuisance mitigation"
    },
    
    # Trees
    "TREE": {
        "description": "Tree violation (dead, diseased, encroaching)",
        "cost_low": 1000,
        "cost_high": 5000,
        "avg": 2000,
        "notes": "Tree removal/trimming"
    },
    
    # Pool/Spa
    "POOL": {
        "description": "Pool/spa violation",
        "cost_low": 2000,
        "cost_high": 10000,
        "avg": 5000,
        "notes": "Fence, safety, drain, maintenance"
    },
    
    # Electrical
    "ELEC": {
        "description": "Electrical code violation",
        "cost_low": 1000,
        "cost_high": 8000,
        "avg": 3000,
        "notes": "Wiring, panel, outlet issues"
    },
    
    # Plumbing
    "PLUMB": {
        "description": "Plumbing violation",
        "cost_low": 2000,
        "cost_high": 8000,
        "avg": 4000,
        "notes": "Pipe, fixture, drain issues"
    },
    
    # Roof
    "ROOF": {
        "description": "Roof damage/violation",
        "cost_low": 8000,
        "cost_high": 20000,
        "avg": 12000,
        "notes": "Missing shingles, leaks, structural damage"
    },
    
    # Window/Door
    "WINDOW": {
        "description": "Window/door violation",
        "cost_low": 1000,
        "cost_high": 5000,
        "avg": 3000,
        "notes": "Broken glass, missing panes, security bars"
    },
    
    # Structural
    "STRUCT": {
        "description": "Structural code violation",
        "cost_low": 10000,
        "cost_high": 30000,
        "avg": 15000,
        "notes": "Foundation, wall damage, major repairs"
    },
    
    # HVAC
    "HVAC": {
        "description": "HVAC violation",
        "cost_low": 2000,
        "cost_high": 8000,
        "avg": 4000,
        "notes": "AC/heating system repair/replacement"
    },
}

def get_repair_cost(violation_type: str, use_low=False, use_high=False) -> float:
    """Get repair cost for violation type."""
    if violation_type not in VIOLATION_REPAIR_MATRIX:
        # Unknown type: use generic average
        return 3000.0
    
    entry = VIOLATION_REPAIR_MATRIX[violation_type]
    
    if use_low:
        return entry["cost_low"]
    elif use_high:
        return entry["cost_high"]
    else:
        return entry["avg"]

def estimate_total_repairs(violation_types: list, contingency_pct=0.20) -> float:
    """
    Estimate total repair cost for property with multiple violations.
    
    Args:
        violation_types: List of violation type codes
        contingency_pct: Add buffer for unknown issues (default 20%)
    
    Returns:
        Estimated total repair cost
    """
    if not violation_types:
        return 0.0
    
    subtotal = sum(get_repair_cost(v) for v in violation_types)
    contingency = subtotal * contingency_pct
    
    return subtotal + contingency
```

**Update ProfitabilityBucket to use new mapping**:

```python
# In profitability.py
from src.wholesaler.scoring.violation_costs import estimate_total_repairs

def _estimate_repairs(self, record: Dict[str, Any]) -> float:
    """Estimate repairs using violation type mapping."""
    violation_types = record.get("violation_types", [])
    
    if violation_types:
        return estimate_total_repairs(violation_types, contingency_pct=0.20)
    else:
        # Fallback: use violation count
        violation_count = record.get("violation_count", 0)
        return violation_count * 3000 * 1.20  # $3K per violation + 20% contingency
```

**Effort**: 2-3 hours

---

### Sprint 3.6.4: Add Market Value Filters (Week 2)

**Objective**: Filter out properties outside investable range

#### Task 3.6.4.1: Add market segment filtering

**File**: `src/wholesaler/scoring/scorers.py` (MODIFY)

Add check before scoring:

```python
def score(self, record: Dict[str, Any]) -> Dict[str, Any]:
    """Score with market segment validation."""
    market_value = record.get("total_mkt")
    
    # Check market segment
    if not market_value or market_value < 80000 or market_value > 500000:
        return {
            "total_score": 0,
            "tier": "D",
            "reason": "out_of_market_segment",
            "market_value": market_value,
        }
    
    # Continue with normal scoring...
```

**Update dashboard to show filter stats**:

```python
# In frontend/pages/stats.py
def show_filter_breakdown():
    """Show how many leads are filtered by market segment."""
    
    stats = {
        "under_80k": db.query(...).filter(Property.total_mkt < 80000).count(),
        "in_market": db.query(...).filter(
            Property.total_mkt >= 80000,
            Property.total_mkt <= 500000
        ).count(),
        "over_500k": db.query(...).filter(Property.total_mkt > 500000).count(),
    }
    
    st.subheader("Market Segment Distribution")
    col1, col2, col3 = st.columns(3)
    col1.metric("Under $80K", stats["under_80k"])
    col2.metric("In Market", stats["in_market"])
    col3.metric("Over $500K", stats["over_500k"])
```

**Effort**: 1-2 hours

---

### Sprint 3.6.5: Testing & Validation (Week 2)

**Objective**: Verify all changes work correctly

#### Task 3.6.5.1: Run full test suite

```bash
make test
make test-cov
```

Expected:
- All existing tests pass
- New profitability tests pass
- Coverage for new modules >80%

**Effort**: 2-3 hours (including fixes)

#### Task 3.6.5.2: Manual testing with sample data

```bash
# Test with real property data
python -m pytest tests/wholesaler/scoring/test_profitability.py -v

# Quick manual test
python -c "
from src.wholesaler.scoring.scorers import HybridBucketScorer
scorer = HybridBucketScorer()
result = scorer.score({
    'parcel_id': 'test',
    'violation_count': 5,
    'total_mkt': 250000,
    'total_assd': 100000,
    'tax_sale': True,
    'violation_types': ['ELEC', 'ROOF'],
})
print(result)
"
```

**Effort**: 1 hour

#### Task 3.6.5.3: Update documentation

**Files to update**:
- `README.md` - Update scoring section with new 4-bucket model
- `FINAL_ARCHITECTURE.md` - Add profitability bucket explanation
- `.github/copilot-instructions.md` - Update scoring pattern examples

**Effort**: 1-2 hours

---

## PHASE 3.6 Summary

| Sprint | Task | Effort | Status |
|--------|------|--------|--------|
| 3.6.1 | Profitability bucket | 6-9h | 📋 Ready |
| 3.6.2 | Fix equity calc | 1-2h | 📋 Ready |
| 3.6.3 | Repair costs by type | 2-3h | 📋 Ready |
| 3.6.4 | Market value filters | 1-2h | 📋 Ready |
| 3.6.5 | Testing & docs | 4-6h | 📋 Ready |
| **Total** | | **14-22 hours** | **2 weeks** |

**Expected Impact**:
- Lead quality improves 60-70%
- Tier A leads have >70% confidence of meeting $15K profit threshold
- False positive rate drops from ~50% to ~20%

---

## PHASE 3.6.B: COMP-BASED ARV (Optional but Recommended)

**Timeline**: After 3.6.1-3.6.5 complete (Weeks 3-4)

**Objective**: Replace 60% fallback with real comparable sales analysis

### Decision: Choose ARV Integration Strategy

**Option A: Zillow API** (Easiest, 3-4 hours)
```python
# Zillow provides Zestimate + Zestimate Low/High
# Free tier available; simple REST API
# Accuracy: 15-25%

def estimate_arv_zillow(address: str) -> float:
    """Get ARV from Zillow Zestimate."""
    z = zillow_api.GetSearchResults(address)
    if z.zestimate:
        return z.zestimate + (z.zestimate * 0.10)  # Add 10% for repairs
    return None
```

**Option B: MLS API** (Better accuracy, 6-8 hours)
```python
# Query recent sales in same neighborhood
# Filter by beds/baths/sqft similarity
# Calculate price per sqft
# Apply to subject property
# Accuracy: 10-15%

def estimate_arv_mls(parcel_id: str, property_details: dict) -> float:
    """Get ARV from MLS comparable sales."""
    comps = mls_api.search(
        city=property_details["city"],
        beds=property_details["beds"],
        baths=property_details["baths"],
        sqft_low=property_details["sqft"] * 0.9,
        sqft_high=property_details["sqft"] * 1.1,
        sold_days_back=180,  # Last 6 months
    )
    
    prices_per_sqft = [c.price / c.sqft for c in comps]
    median_price_per_sqft = median(prices_per_sqft)
    
    estimated_arv = median_price_per_sqft * property_details["sqft"]
    return estimated_arv * 1.10  # Add 10% for repairs
```

**Option C: HedgeAPI** (Hybrid, 4-5 hours)
```python
# Combines multiple sources (Zillow, tax assessment, comps)
# More accurate than single source
# Accuracy: 12-18%

def estimate_arv_hedge(parcel_id: str) -> float:
    """Get ARV from HedgeAPI (multi-source)."""
    result = hedge_api.get_value(parcel_id)
    return result["estimated_value"] * 1.10
```

**Recommendation**: Start with **Option A (Zillow)** for quick win, then integrate **Option B (MLS)** for accuracy.

---

## PHASE 4: CONTACT ENRICHMENT & OUTREACH (2-3 months)

⚠️ **CRITICAL BLOCKER**: System cannot execute outreach without contact information.

### Phase 4A: Skip Tracing Infrastructure (Weeks 1-2)

**Objective**: Extract owner phone/email from public records

#### Task 4A.1: Evaluate skip tracing options

**Options**:
1. **Manual web scraping** ($0, high effort, risky)
2. **Skip tracing service API** ($0.50-$2.00 per lead)
   - Realtor.com
   - SkyMinder
   - TrueCaller Business
3. **DIY with BeautifulSoup** ($0, medium effort)
   - Orange County Property Appraiser website
   - Orange County Tax Assessor
   - LinkedIn for owner names

**Recommendation**: Hybrid approach
- **Phase 1**: DIY scraping of public property appraiser sites (~40% success rate)
- **Phase 2**: Integrate with paid service for misses (~90% total success rate)

#### Task 4A.2: Implement property appraiser scraper

**File**: `src/wholesaler/scrapers/contact_scraper.py` (NEW)

```python
"""
Contact information extractor for property owners.

Scrapes public records from Orange County Property Appraiser website.
"""
from typing import Optional, Dict
from selenium import webdriver
from bs4 import BeautifulSoup
import re


class ContactScraper:
    """Extract owner contact info from property appraiser website."""
    
    def get_owner_info(self, parcel_id: str) -> Optional[Dict[str, str]]:
        """
        Get owner information from Orange County Property Appraiser.
        
        Args:
            parcel_id: Normalized parcel ID
        
        Returns:
            {"owner_name": str, "mailing_address": str, "phone": str, "email": str}
            or None if not found
        """
        url = f"https://ocpafl.org/search/records?parcel={parcel_id}"
        
        driver = webdriver.Chrome()
        try:
            driver.get(url)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Extract from page (exact selectors depend on site structure)
            owner_name = soup.find('div', {'class': 'owner-name'})
            mailing_address = soup.find('div', {'class': 'mailing-address'})
            
            # Try to find phone/email in various formats
            page_text = soup.get_text()
            phone = self._extract_phone(page_text)
            email = self._extract_email(page_text)
            
            return {
                "owner_name": owner_name.text if owner_name else None,
                "mailing_address": mailing_address.text if mailing_address else None,
                "phone": phone,
                "email": email,
            }
        finally:
            driver.quit()
    
    @staticmethod
    def _extract_phone(text: str) -> Optional[str]:
        """Extract phone number from text."""
        match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
        return match.group(0) if match else None
    
    @staticmethod
    def _extract_email(text: str) -> Optional[str]:
        """Extract email from text."""
        match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
        return match.group(0) if match else None
```

**Effort**: 4-6 hours (including debugging with actual website)

#### Task 4A.3: Add contact data to database

**File**: `src/wholesaler/db/models.py` (MODIFY)

Add new `Contact` table:

```python
class Contact(Base, TimestampMixin):
    """Owner contact information."""
    __tablename__ = "contacts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    parcel_id_normalized: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("properties.parcel_id_normalized"),
        unique=True,
    )
    
    owner_name: Mapped[Optional[str]] = mapped_column(String(255))
    mailing_address: Mapped[Optional[str]] = mapped_column(String(500))
    phone: Mapped[Optional[str]] = mapped_column(String(20))  # E.164 format
    email: Mapped[Optional[str]] = mapped_column(String(255))
    
    phone_verified: Mapped[bool] = mapped_column(default=False)
    email_verified: Mapped[bool] = mapped_column(default=False)
    
    contact_source: Mapped[str] = mapped_column(String(50))  # "scraper", "paid_service", "manual"
    last_contacted: Mapped[Optional[datetime]] = mapped_column(DateTime)
    opted_out: Mapped[bool] = mapped_column(default=False)
    opted_out_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    property: Mapped["Property"] = relationship(back_populates="contact")
```

**Effort**: 2-3 hours (including migration)

---

### Phase 4B: CRM Infrastructure (Weeks 2-3)

**Tables**: Campaigns, Communications, ConversationStates, LeadStatuses

*(Details in PHASE_4_OVERVIEW.md - just linking here)*

**Effort**: 20-30 hours

---

### Phase 4C-4F: Multi-Channel Outreach Engine (Weeks 4-12)

See `PHASE_4_OVERVIEW.md` for detailed specs.

**Effort**: 40-60 hours total (phased)

---

## Implementation Timeline

```
WEEK 1-2 (Dec 2-15):     Phase 3.6.1 - Profitability bucket
WEEK 2 (Dec 9-15):       Phase 3.6.2-3.6.4 - Equity, repairs, filters
WEEK 2-3 (Dec 9-20):     Phase 3.6.5 - Testing & docs
WEEK 3-4 (Dec 16-29):    Phase 3.6.B - Comp-based ARV (optional)
--
WEEK 5-6 (Jan 6-19):     Phase 4A.1-4A.3 - Contact enrichment
WEEK 7-8 (Jan 20-Feb 2): Phase 4B - CRM tables & APIs
WEEK 9-12 (Feb 3-March 2): Phase 4C-4F - Outreach engine & AI agents
```

---

## Resource Requirements

### Development Time
- **Phase 3.6**: 14-22 hours (1 developer, 2 weeks part-time)
- **Phase 3.6.B**: 3-8 hours (optional comp analysis)
- **Phase 4A**: 6-8 hours (contact scraping)
- **Phase 4B-4F**: 40-60 hours (2-3 months, can parallelize)

### External Services
- **Zillow/MLS API**: Free tier or ~$50-200/month
- **Skip tracing service**: ~$0.50-2.00 per lead (optional fallback)
- **Twilio SMS**: ~$0.0075 per SMS (free trial $15)
- **Ollama LLM**: $0 (self-hosted)

### Infrastructure
- **GPU for Ollama**: Optional (can run on CPU)
- **Redis**: Already deployed
- **PostgreSQL**: Already deployed

---

## Risk Mitigation

| Risk | Mitigation | Effort |
|------|-----------|--------|
| Profitability changes break existing code | Comprehensive test suite (Phase 3.6.5) | 3-4h |
| ARV estimates still unreliable | Validate against actual outcomes (Phase 4+) | Ongoing |
| Skip tracing low success rate | Fallback to paid service for misses | 2-3h |
| LLM hallucinations in messages | Prompt engineering + manual review of first 50 | 5-10h |
| TCPA violations in SMS outreach | Automatic DNC check + opt-out handling | 4-6h |

---

## Go/No-Go Decision Gates

| Gate | Condition | Timeline |
|------|-----------|----------|
| **Gate 1**: Profitability validation working | Phase 3.6.1 tests pass, lead quality improves 60%+ | Dec 15 |
| **Gate 2**: ARV accuracy acceptable | Comp analysis deployed, ±20% accuracy | Jan 10 |
| **Gate 3**: Contact extraction viable | >50% success rate on property appraiser scraping | Jan 25 |
| **Gate 4**: Outreach automation ready | Phase 4B/4C complete, CRM operational | Feb 15 |
| **Gate 5**: ML models reliable | Sent 50 messages, <5% spam complaints | Feb 28 |

If any gate fails, escalate and adjust timeline.

---

## Success Metrics (Post-Implementation)

```
PHASE 3.6 SUCCESS (by Jan 20):
├─ Tier A leads have >70% confidence of $15K+ profit
├─ False positive rate drops from 50% → 20%
├─ ARV estimates within ±20% of comps
└─ Lead volume by segment clearly measured

PHASE 4 SUCCESS (by March 15):
├─ Contact extraction >70% success rate
├─ Campaigns executing on schedule
├─ Response rate >3% from contacted leads
├─ Deal close rate >5% of leads contacted
├─ Profit per deal within ±15% of projections
└─ ROI on outreach >300:1 (cost per lead $50 → $15K profit)
```

---

## Next Steps

1. **Approve roadmap** - Does this align with your priorities?
2. **Allocate resources** - Developer time for Phases 3.6 and 4A?
3. **Set up dependencies** - Twilio account, MLS API access, Ollama setup?
4. **Create tickets** - Break each task into JIRA/GitHub issues?
5. **Begin Phase 3.6.1** - Start with profitability bucket immediately?

---

**Roadmap Version**: 1.0  
**Created**: November 15, 2025  
**Status**: READY FOR EXECUTION  
**Next Review**: December 1, 2025
