# Quick Start Guide - New Location Features

## ðŸš€ Try It Now

### Step 1: Launch the Application

```powershell
powershell -ExecutionPolicy Bypass -File launch.ps1

```

### Step 2: Open Your Browser

Navigate to: **http://127.0.0.1:8080**

### Step 3: Try These Example Queries

#### Example 1: Montreal with Postal Code

1. Select **Montreal** from the City dropdown
2. Enter postal code: **H3A1A1**
3. Set budget: **$100**
4. Max items: **8**
5. Click **Generate plan**

**You'll see:**

- Your optimized grocery list ($39.85)
- 5 nearby stores with distances (0.98 km to 7.67 km)
- Price comparison across all stores
- Optimized route visiting all stores (14.05 km total)

#### Example 2: New York

1. Select **New York, NY**
2. Enter postal code: **10001**
3. Set budget: **$150** (USD)
4. Max items: **10**
5. Click **Generate plan**

**You'll see:**

- Optimized list adjusted for NYC pricing (+35% higher)
- 4 nearby stores (Whole Foods, Trader Joe's, Fairway, ALDI)
- Premium vs budget store price differences
- Route from your location through all stores

#### Example 3: Toronto

1. Select **Toronto, ON**
2. Enter postal code: **M5H2N2**
3. Set budget: **$80** (CAD)
4. Max items: **8**
5. Click **Generate plan**

**Discover:**

- Toronto-specific pricing (+8% vs Montreal)
- Loblaws, Metro, No Frills, Wholesale Club nearby
- Budget options (No Frills) vs mid-tier (Loblaws)

## ðŸ—ºï¸ Available Test Postal Codes

### Canada

- **Montreal, QC**: H3A1A1, H2X1Y5, H4B2M9
- **Toronto, ON**: M5H2N2, M4C1B5, M6G1B7

### United States

- **New York, NY**: 10001, 10003, 10014
- **Los Angeles, CA**: 90001, 90012, 90028

## ðŸª Understanding Store Tiers

### Budget Stores (15% discount)

- Super C, Maxi (Montreal)
- No Frills (Toronto)
- ALDI (New York)
- Food 4 Less (Los Angeles)

### Mid-Tier Stores (standard pricing)

- IGA, Metro, Provigo (Montreal)
- Loblaws, Metro (Toronto)
- Trader Joe's, Fairway (New York)
- Trader Joe's, Ralphs (Los Angeles)

### Premium Stores (25% premium)

- Whole Foods (New York, Los Angeles)

**Quality Ratings**: 1.0 to 5.0 stars
**Value Score**: Quality per $10 spent

## ðŸ“Š Reading Your Results

### Summary Cards

- **Total Cost**: What you'll pay for this plan
- **Money Left**: Budget remaining
- **Items**: Number of items in your cart
- **Avg Freshness**: Average shelf life of items

### Store Comparison Table

Shows each nearby store with:

- **Name & Chain**: Store identity
- **Distance**: How far from your postal code (km)
- **Price Tier**: budget/mid/premium
- **Quality**: Star rating out of 5.0
- **Est. Total**: What this plan would cost at that store
- **Value**: Quality-to-price ratio

### Optimized Route

- **Origin**: Your starting postal code
- **Stops**: Stores in optimal visit order
- **Distance from previous**: km between each stop
- **Total**: Total km for the entire route

## ðŸ’¡ Pro Tips

1. **Try different postal codes** in the same city to see how store options change
2. **Compare cities** - notice how NYC is more expensive than Montreal
3. **Look at value scores** to find best quality-to-price ratio
4. **Use the route** to plan efficient multi-store trips
5. **Budget stores** can save 15% but may have slightly lower quality
6. **Save your plans** (requires creating an account)

## ðŸ”§ API Examples

### Get Nearby Stores

```bash
curl http://127.0.0.1:8000/stores?postal_code=H3A1A1

```

### Get Postal Codes

```bash
curl http://127.0.0.1:8000/postal-codes?country=CA

```

### Optimize with Postal Code

```bash
curl -X POST http://127.0.0.1:8000/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "budget": 100,
    "max_items": 8,
    "location": "montreal",
    "postal_code": "H3A1A1"
  }'

```

## â“ FAQ

**Q: What if I don't enter a postal code?**
A: You'll still get an optimized grocery plan, just without the store comparison and route features.

**Q: Can I add my own stores?**
A: Yes! Edit the JSON files in `config/stores/` to add new stores. Include name, address, coordinates, price tier, and quality rating.

**Q: How accurate are the prices?**
A: Prices are estimates based on store tier multipliers. Real prices would need live API integration with actual stores.

**Q: Can I add more cities?**
A: Absolutely! Create new files in `config/locations/`, `config/stores/`, and `config/postal_codes/` following the existing format.

**Q: What if my postal code isn't in the list?**
A: The current database has sample postal codes for demonstration. You can add more to the JSON files.

**Q: How is the route optimized?**
A: Uses a nearest-neighbor algorithm that starts from your location and visits the closest unvisited store at each step.

## ðŸŽ¯ Next Steps

1. **Try all 4 cities** to see price differences
2. **Compare budgets** - see how plan changes with different amounts
3. **Experiment with strategies** - greedy vs knapsack
4. **Save your favorite plans** - create an account on the Account page
5. **Explore the API** - build your own integrations

Enjoy your optimized grocery shopping! ðŸ›’
