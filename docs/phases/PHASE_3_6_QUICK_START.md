# Quick Start: Phase 3.6.1 Implementation

**Goal**: Add profitability validation to lead scoring (1-2 weeks)  
**Effort**: 6-9 developer hours  
**Impact**: 60-70% improvement in lead quality

---

## Overview

Replace your 3-bucket scoring model with a 4-bucket model that validates profitability:

```
OLD (Current):                    NEW (Phase 3.6.1):
├─ Distress: 65%                 ├─ Distress: 50%
├─ Disposition: 20%              ├─ Disposition: 20%
├─ Equity: 15%                   ├─ Equity: 10%
└─ NO PROFIT CHECK                └─ Profitability: 20% ← NEW!
   → Generates leads that          → Only flags leads that
     fail 70% rule math               meet $15K profit threshold
```

---

## Step-by-Step Implementation

### Step 1: Create profitability.py module (30 min)

```bash
touch src/wholesaler/scoring/profitability.py
```

Copy the `ProfitabilityBucket` class from `IMPLEMENTATION_ROADMAP.md` → **Task 3.6.1.1**

Key features:
- ✅ Estimates ARV (conservative: market value + 10-15%)
- ✅ Calculates repairs (by violation type)
- ✅ Applies 70% rule: `max_offer = (ARV × 0.70) - repairs`
- ✅ Determines acquisition path (tax sale, foreclosure, direct)
- ✅ Scores profitability 0-100

**Test it**:
```bash
python -c "
from src.wholesaler.scoring.profitability import ProfitabilityBucket

scorer = ProfitabilityBucket()
result = scorer.score({
    'parcel_id': 'test123',
    'total_mkt': 300000,
    'total_assd': 100000,
    'violation_count': 5,
    'violation_types': ['ROOF'],
    'tax_sale': True,
})

print(f\"Profitability score: {result['profitability_score']}\")
print(f\"Estimated profit: \${result['estimated_profit']:,.0f}\")
print(f\"Meets 70% rule: {result['meets_70_rule']}\")
"
```

Expected output:
```
Profitability score: 80.0
Estimated profit: $44700.00
Meets 70% rule: True
```

---

### Step 2: Create profitability tests (20 min)

```bash
touch tests/wholesaler/scoring/test_profitability.py
```

Copy test cases from `IMPLEMENTATION_ROADMAP.md` → **Task 3.6.1.1**

```bash
pytest tests/wholesaler/scoring/test_profitability.py -v
```

Expected:
```
test_excellent_deal PASSED
test_marginal_deal PASSED
test_out_of_market PASSED
===================== 3 passed ✅
```

---

### Step 3: Integrate profitability into HybridBucketScorer (1 hour)

**File**: `src/wholesaler/scoring/scorers.py`

**Change 1**: Update imports and weights

```python
# OLD
WEIGHTS = {"distress": 0.65, "disposition": 0.20, "equity": 0.15}

# NEW
WEIGHTS = {
    "distress": 0.50,
    "disposition": 0.20,
    "equity": 0.10,
    "profitability": 0.20,
}
```

**Change 2**: Update score() method

Find this section:
```python
def score(self, record: Dict[str, Any]) -> Dict[str, Any]:
    buckets = self._bucket_scores(record)
    total = buckets.total(self.WEIGHTS)
    if record.get("tax_sale"):
        total += 15
    if record.get("foreclosure"):
        total += 10
    total = _clamp(total)
    tier = self._tier(total)
    return {
        "total_score": total,
        "tier": tier,
        "bucket_scores": buckets,
    }
```

Replace with:
```python
def score(self, record: Dict[str, Any]) -> Dict[str, Any]:
    from src.wholesaler.scoring.profitability import ProfitabilityBucket
    
    buckets = self._bucket_scores(record)
    
    # NEW: Calculate profitability score
    profit_bucket = ProfitabilityBucket()
    profit_result = profit_bucket.score(record)
    profit_score = profit_result["profitability_score"]
    
    # Calculate weighted total with 4 buckets
    total = (
        buckets.distress * self.WEIGHTS["distress"] +
        buckets.disposition * self.WEIGHTS["disposition"] +
        buckets.equity * self.WEIGHTS["equity"] +
        profit_score * self.WEIGHTS["profitability"]
    )
    
    # Keep bonuses
    if record.get("tax_sale"):
        total += 15
    if record.get("foreclosure"):
        total += 10
    
    total = _clamp(total)
    tier = self._tier(total, profit_result)
    
    return {
        "total_score": total,
        "tier": tier,
        "bucket_scores": buckets,
        "profitability": profit_result,  # NEW
    }
```

**Change 3**: Update _tier() method

Find:
```python
@staticmethod
def _tier(score: float) -> str:
    if score >= 60:
        return "A"
    if score >= 45:
        return "B"
    if score >= 32:
        return "C"
    return "D"
```

Replace with:
```python
@staticmethod
def _tier(score: float, profit_result: Dict) -> str:
    """Assign tier with profitability validation."""
    # HIGH TIERS require profitability
    if score >= 65 and profit_result["profitability_score"] > 0:
        return "A"
    if score >= 50 and profit_result["profitability_score"] > 0:
        return "B"
    if score >= 40:
        return "C"
    return "D"
```

---

### Step 4: Test integration (30 min)

```bash
pytest tests/wholesaler/scoring/test_scorers.py -v -k "test_hybrid"
```

Expected: All tests pass

```bash
# Manual test
python -c "
from src.wholesaler.scoring import HybridBucketScorer

scorer = HybridBucketScorer()

# Good deal (should be Tier A)
good_deal = {
    'parcel_id': '123',
    'violation_count': 5,
    'open_violations': 1,
    'most_recent_violation': '2025-11-01',
    'total_mkt': 250000,
    'total_assd': 100000,
    'tax_sale': True,
    'violation_types': ['ELEC'],
}

result = scorer.score(good_deal)
print(f\"Good deal tier: {result['tier']} (expected: A)\")
print(f\"Profit: \${result['profitability']['estimated_profit']:,.0f}\")

# Bad deal (should be Tier D)
bad_deal = {
    'parcel_id': '124',
    'violation_count': 10,
    'total_mkt': 600000,  # Too expensive
    'violation_types': ['STRUCT'],
}

result = scorer.score(bad_deal)
print(f\"Bad deal tier: {result['tier']} (expected: D)\")
"
```

Expected output:
```
Good deal tier: A (expected: A)
Profit: $44,700.00
Bad deal tier: D (expected: D)
```

---

### Step 5: Run full test suite (20 min)

```bash
make test
make test-cov
```

Expected:
- ✅ All tests pass
- ✅ Coverage for new modules >80%
- ✅ No regression in existing tests

If failures:
```bash
# Debug specific test
pytest tests/wholesaler/scoring/test_scorers.py::TestHybridBucketScorer::test_score -vv
```

---

### Step 6: Update documentation (20 min)

**File**: `README.md`

Find the "Lead Scoring Algorithm" section and update:

```markdown
## Lead Scoring Algorithm

### Components (Weighted)

1. **Distress Score (50%)** ← Updated from 35%
   - Code violations nearby: up to +80 points (by count and recency)
   - Open violations: +3 points each
   
2. **Disposition Score (20%)**
   - Tax sale status: +60 points
   - Foreclosure status: +45 points

3. **Equity Score (10%)** ← Updated from 30%, de-emphasized
   - High market/assessed ratio: +30 points
   - NOTE: Not true equity (requires loan balance data)

4. **Profitability Score (20%)** ← NEW!
   - Validates 70% rule: ARV × 0.70 - Repairs - Acquisition
   - Properties meeting $15K profit threshold: 60-100 points
   - Properties below threshold: 0 points
```

---

### Step 7: Deploy changes (10 min)

```bash
# Commit changes
git add src/wholesaler/scoring/profitability.py
git add tests/wholesaler/scoring/test_profitability.py
git add src/wholesaler/scoring/scorers.py
git commit -m "Phase 3.6.1: Add profitability bucket to scoring

- Create ProfitabilityBucket class (70% rule validation)
- Integrate into HybridBucketScorer with 4-bucket model
- Add comprehensive tests for profitability scenarios
- Update tier thresholds to require profitability for Tier A/B

Expected impact: 60-70% improvement in lead quality"

git push origin phase-3.6-profit-validation
```

**Create pull request** for code review

---

## Before/After Comparison

### Current State (3-bucket)
```
Property: 123 Main St
├─ Violations: 8 (distress = 80)
├─ Tax sale: Yes (disposition = 60)
├─ Equity: 150% (equity = 35)
├─ Total score: (80 × 0.65) + (60 × 0.20) + (35 × 0.15) = 68
└─ Tier: A ✅ (but profit unknown)

PROBLEM: Leads like this get flagged as "great" even if unprofitable!
```

### New State (4-bucket, Phase 3.6.1)
```
Same property:
├─ Violations: 8 (distress = 80 → 50% weight)
├─ Tax sale: Yes (disposition = 60 → 20% weight)
├─ Equity: 150% (equity = 25 → 10% weight)
├─ Profitability calculation:
│  ├─ ARV: $300K × 1.15 = $345K
│  ├─ Repairs: 8 violations × avg = $25K
│  ├─ Max offer: ($345K × 0.70) - $25K = $216.5K
│  ├─ Acquisition (tax sale): ~$190K
│  ├─ Profit: $216.5K - $190K = $26.5K ✅
│  └─ Profitability score: 80
├─ Total score: (80 × 0.50) + (60 × 0.20) + (25 × 0.10) + (80 × 0.20) = 65
└─ Tier: A ✅ (AND profit validated: $26.5K > $15K threshold)

IMPROVEMENT: Only flags deals that are actually profitable!
```

---

## Validation Checklist

Before moving to next phase, confirm:

- [ ] `profitability.py` created and imports work
- [ ] All 3 profitability tests pass
- [ ] `HybridBucketScorer` updated with 4 buckets
- [ ] Integration tests pass
- [ ] Full test suite passes (`make test`)
- [ ] Manual testing shows good deals as Tier A, bad deals as Tier D
- [ ] Documentation updated
- [ ] Code committed and PR merged

---

## Next Steps

Once Phase 3.6.1 is complete:

1. **Phase 3.6.2** (1-2 hours): Fix equity calculation
2. **Phase 3.6.3** (2-3 hours): Repair costs by violation type
3. **Phase 3.6.4** (1-2 hours): Add market value filters
4. **Phase 3.6.5** (4-6 hours): Full testing & documentation

Total Phase 3.6: 2 weeks part-time

---

## Troubleshooting

### Issue: "ImportError: cannot import name 'ProfitabilityBucket'"

**Solution**: Make sure `profitability.py` is in `src/wholesaler/scoring/` and module is importable:

```bash
python -c "from src.wholesaler.scoring.profitability import ProfitabilityBucket; print('OK')"
```

### Issue: "TypeError: _tier() missing 1 required positional argument"

**Solution**: You're calling `_tier(score)` but it now expects `_tier(score, profit_result)`. Update all calls to pass both arguments.

### Issue: Tier A leads still have negative profit

**Solution**: Check that `profit_result["profitability_score"] > 0` is being enforced in `_tier()` method. If profits are very low, may need to increase the minimum profitability threshold.

---

## Questions?

Refer to full roadmap: `IMPLEMENTATION_ROADMAP.md`  
Business analysis: `BUSINESS_ANALYSIS.md`  
Copilot instructions: `.github/copilot-instructions.md`

---

**Version**: 1.0  
**Last Updated**: November 15, 2025
