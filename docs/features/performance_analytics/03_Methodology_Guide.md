# Methodology Guide: Performance Analytics

This guide details the financial methodologies used by the `query_service` to calculate Time-Weighted Return (TWR) and Money-Weighted Return (MWR). All calculations are performed on-the-fly using the data from the `portfolio_timeseries` table.

## 1. Time-Weighted Return (TWR)

Time-Weighted Return measures the compound rate of growth in a portfolio. It is the industry standard for judging the performance of a portfolio manager because it **eliminates the distorting effects of external cash flows**.

The system uses a proprietary, stateful, day-by-day calculation engine. This methodology is designed to be highly robust, correctly handling complex scenarios such as short positions (negative market value) and total "wipeouts" where a position loses more than 100% of its value.

### Core Concept: Long/Short Performance Sleeves

The engine's fundamental design principle is the separation of performance into two distinct "sleeves":

* **Long Sleeve:** Tracks the geometric return during periods when the portfolio's market value is positive.
* **Short Sleeve:** Tracks the geometric return during periods when the portfolio's market value is negative.

Each day, the total cumulative TWR is calculated by geometrically linking the returns from these two sleeves.

### The Daily Calculation Loop

For each day in the requested period, the engine performs the following stateful calculations:

**Step A: Determine Portfolio Sign (`SIGN`)**
The engine first determines if the portfolio is in a long or short state based on the beginning-of-day capital.
* If `MV_BOD + CF_BOD` > 0, the `SIGN` is `1` (Long).
* If `MV_BOD + CF_BOD` < 0, the `SIGN` is `-1` (Short).
* If `0`, the `SIGN` is `0`.

**Step B: Calculate Daily Rate of Return (`DAILY_ROR_PCT`)**
A standard daily return is calculated based on the `net_or_gross` scope. For a `NET` calculation:
$$
R_{day, NET} = \frac{MV_{EOD} - MV_{BOD} - (\text{CF}_{BOD} + \text{CF}_{EOD}) + \text{Fees}}{MV_{BOD} + \text{CF}_{BOD}}
$$

**Step C: Link Daily Return into the Active Sleeve**
The `DAILY_ROR_PCT` is geometrically linked into the temporary accumulator for the **active sleeve only**.
* If `SIGN` is `1`, `TEMP_LONG_CUM_ROR_PCT` is updated.
* If `SIGN` is `-1`, `TEMP_SHORT_CUM_ROR_PCT` is updated.
The inactive sleeve's temporary accumulator is reset to zero.

**Step D: Check for Performance Resets (`PERF_RESET`)**
The engine checks for "wipeout" conditions that trigger a hard reset of a sleeve's performance to prevent nonsensical results. A `PERF_RESET` flag is triggered if, on a day with cash flow or at month-end:
* The long sleeve's cumulative return drops below -100%.
* The short sleeve's cumulative return exceeds +100% (indicating a loss greater than the initial value of the short position).

**Step E: Finalize Sleeve Returns (`LONG_CUM_ROR_PCT`, `SHORT_CUM_ROR_PCT`)**
If the `PERF_RESET` flag is triggered, the corresponding sleeve's final cumulative return for the day is reset to zero. Otherwise, it takes the value from the temporary accumulator calculated in Step C.

**Step F: Combine Sleeves for Final TWR**
The final cumulative TWR for the day is calculated by linking the final values of the long and short sleeves.
$$
\text{TWR}_{day} = \left[ (1 + \frac{\text{LONG\_CUM\_ROR\_PCT}}{100}) \times (1 + \frac{\text{SHORT\_CUM\_ROR\_PCT}}{100}) \right] - 1
$$
This combined value is then carried forward to the next day's calculation.

---

## 2. Money-Weighted Return (MWR)

Money-Weighted Return measures a portfolio's internal rate of return (IRR). Unlike TWR, it **is influenced by the timing and size of cash flows**. It represents the constant rate of return that would be required for the initial investment, plus all subsequent cash flows, to equal the final market value.

### Calculation Methodology (XIRR)

The system calculates MWR by solving for the rate ($r$) in the Net Present Value (NPV) equation:

$$
0 = \sum_{i=1}^{n} \frac{C_i}{(1+r)^{(d_i - d_1)/365}}
$$

To solve for $r$, the service performs these steps:

1.  **Construct a Cash Flow Timeline:** It creates a timeline of all flows from the investor's perspective:
    * The Beginning Market Value is treated as the initial outflow (negative).
    * All external deposits (`CASHFLOW_IN`) are treated as outflows (negative).
    * All external withdrawals (`CASHFLOW_OUT`) are treated as inflows (positive).
    * The Ending Market Value is treated as the final inflow (positive).
2.  **Solve for the Rate:** It uses an iterative numerical solver (Newton-Raphson) to find the discount rate ($r$) that makes the sum of the present values of all cash flows equal to zero. This rate is the MWR.