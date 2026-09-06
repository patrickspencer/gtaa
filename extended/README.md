# Extended backtest, 2000–present

The main backtest starts in 2014 because that is when every ETF in the
universe has a year of history. This directory pushes the start back to
**August 2000** by splicing a mutual fund in front of each ETF, which buys
fourteen more years (two bear markets, 2000–02 and 2008, a commodity boom
and a full rate cycle) at the cost of some fidelity.

**Read the results as less reliable than the 2014 ones.** Before each switch
date the strategy is trading a fund that is *similar to* the ETF, not the
ETF, and for three of the fourteen sleeves the substitute is a different
kind of thing altogether (see the notes under the table). The 2014 backtest
answers "what would this portfolio of ETFs have done"; this one answers
"what would the rules have done on the closest tradable funds that existed".

The rules themselves are unchanged from the main backtest and come from
Faber's [*A Quantitative Approach to Tactical Asset Allocation*](https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf).

```bash
python extended/build.py                         # ~1 min, writes extended.duckdb
gtaa --db extended.duckdb backtest --top 6 --years
gtaa --db extended.duckdb backtest --top 3 --years
```

## How the splice works

For each asset class, `build.py` fetches the ETF and its proxy fund from
Tiingo, both as adjusted (total-return) daily closes. Every date before the
ETF's first trading day is taken from the fund, scaled so that the fund and
the ETF agree on that first day. Both sides keep their own returns exactly;
only the fund's level is rescaled, and the join itself contributes no
return. The spliced series is stored under the ETF's symbol, so the signal
query and backtest in `gtaa/` run on it unchanged, and a `sources` table
in the database records which fund supplied which dates.

The switch happens on the ETF's first day, not later, so the ETF period of
this backtest is identical to the main one: from 2015 on, the calendar-year
numbers below match the main README to the basis point.

## The proxies and when they hand over

The rule for choosing a proxy: **the same fund in an older share class**
where one exists (Vanguard's index ETFs are share classes of mutual funds
that predate them, so eight of the fourteen are exact), otherwise the
longest-lived, lowest-cost fund tracking the same asset class. Only funds
with daily NAV history on Tiingo were considered.

| Asset class | ETF | Proxy until | Proxy fund | Why |
|---|---|---|---|---|
| US large-cap value | VTV | 2004-01-30 | **VIVAX** Vanguard Value Index Investor | Same fund, older share class. |
| US large-cap momentum | MTUM | 2013-04-18 | **VFINX** Vanguard 500 Index | No momentum fund existed before 2013. Plain large caps are the neutral stand-in; see note 1. |
| US small-cap value | VBR | 2004-01-30 | **VISVX** Vanguard Small-Cap Value Index Investor | Same fund. Starts 1998-05, early enough. |
| US small-cap | VB | 2004-01-30 | **NAESX** Vanguard Small-Cap Index Investor | Same fund. |
| Foreign developed equities | VEA | 2007-07-26 | **VTMGX** Vanguard Developed Markets Index | Same fund. It began in August 1999, and it is the youngest proxy, so it sets the backtest start: twelve months later, August 2000. |
| Emerging-market equities | VWO | 2005-03-10 | **VEIEX** Vanguard Emerging Markets Stock Index Investor | Same fund. |
| US intermediate Treasuries | IEF | 2002-07-26 | **VFITX** Vanguard Intermediate-Term Treasury Investor | Actively managed but Treasury-only with a 5–6 year duration, close to IEF's 7–10 year ladder. |
| US long-term Treasuries | TLT | 2002-07-26 | **VUSTX** Vanguard Long-Term Treasury Investor | Same as above for the long end. |
| Foreign government bonds | BWX | 2007-10-11 | **RPIBX** T. Rowe Price International Bond | The oldest unhedged developed-market sovereign bond fund with continuous history (1986). It holds some corporates and EM; BWX does not. |
| US corporate bonds | LQD | 2002-07-26 | **VFICX** Vanguard Intermediate-Term Investment-Grade Investor | Investment-grade corporates. LQD's duration (~8 years) sits between this fund and Vanguard's long-term fund; the intermediate one was chosen as the more conservative of the two. |
| Commodities | DBC | 2006-02-06 | **QRAAX** Oppenheimer Real Asset A | See note 2. |
| Gold | GLD | 2004-11-18 | **FSAGX** Fidelity Select Gold | See note 3. |
| Real estate | VNQ | 2004-09-29 | **VGSIX** Vanguard REIT Index Investor | Same fund. |
| Cash | BIL | 2007-05-30 | **VFISX** Vanguard Short-Term Treasury Investor | See note 4. |

Investor-class mutual fund shares charged more than the ETFs do today
(roughly 0.2–0.3% a year for the Vanguard index funds in the early 2000s,
around 1% for the active bond and commodity funds), so the proxy period
slightly understates what the same exposures would return at today's costs.

### Notes on the substitutes that are not the same thing

1. **Momentum (MTUM ← VFINX).** Before 2013 this sleeve is the S&P 500, with
   no factor tilt. The strategy still ranks it and applies the trend filter,
   so it behaves as a fifth broad equity sleeve rather than a momentum one.
   This is the largest single departure from the rules in the proxy period;
   Faber's own index study used a momentum series here. A large-cap growth
   fund was considered and rejected: growth and momentum overlap only some
   of the time and the mismatch would be harder to reason about than a plain
   index.
2. **Commodities (DBC ← QRAAX).** Oppenheimer Real Asset tracked the GSCI
   through structured notes and futures, and the GSCI is energy-heavy, so
   the 2000–2006 commodity sleeve is closer to Faber's original GSCI series
   than to DBC's diversified basket. It carried a high expense ratio and
   was liquidated in 2016, which is why it is not used past DBC's launch.
   PIMCO CommodityRealReturn (PCRAX, 2002) was the alternative; it collateralises
   futures with TIPS, which adds a bond return to the series, and it starts
   three years later, so it would have moved the whole backtest start to
   2003.
3. **Gold (GLD ← FSAGX).** No bullion fund existed before GLD. Fidelity
   Select Gold holds gold-mining *stocks*, which move with gold but with
   roughly twice the amplitude and an equity-market component on top. In
   2000–2004 the gold sleeve is therefore more volatile than bullion was,
   and it is exposed to the 2000–02 equity bear market in a way bullion was
   not. Miners also score higher on momentum when gold rises, so the sleeve
   was probably selected more often than bullion would have been.
4. **Cash (BIL ← VFISX).** Money-market funds have a constant NAV, so their
   return cannot be recovered from a price series. Vanguard's short-term
   Treasury fund has a duration of about two years, so cash earns a little
   duration return in the 2001–03 rate cuts and gives some back in 2004–06.
   The effect on the strategy is small (cash averages under 10% of the
   portfolio) but it is there.

## Results

`gtaa --db extended.duckdb backtest --top 6 --years` on data through
August 2026:

```
GTAA AGG 6: 2000-08 to 2026-08 (312 months, month-end to month-end)

Strategy (top 6 by momentum, trend filter, rest in cash)
  CAGR                     10.23%
  Max drawdown            -12.78%
  Volatility (annual)       9.76%
  Sharpe (vs T-bills)        0.82
  Best month                8.17%
  Worst month              -9.75%
  Average cash weight        7.6%

Equal-weight (all 13 held at once, 1/13 each, rebalanced monthly)
  CAGR                      7.76%
  Max drawdown            -34.47%
  Volatility (annual)      10.60%
  Sharpe (vs T-bills)        0.55
  Best month                8.41%
  Worst month             -15.72%

Calendar years:
         strategy   equal-weight
  2000      0.57%         -0.54%  (from Sep)
  2001      2.31%         -0.62%
  2002     12.77%          3.95%
  2003     31.53%         27.50%
  2004     11.78%         15.39%
  2005      6.54%         10.34%
  2006     24.10%         15.76%
  2007     12.65%          9.51%
  2008     -1.73%        -20.46%
  2009     16.85%         20.83%
  2010     13.08%         17.04%
  2011      5.08%          3.71%
  2012      8.79%         12.34%
  2013     23.92%          5.82%
  2014      9.28%          5.68%
  2015     -8.11%         -4.48%
  2016      7.47%          9.97%
  2017     18.84%         14.50%
  2018     -1.72%         -6.08%
  2019      8.03%         19.58%
  2020     11.92%         12.01%
  2021     22.13%         11.47%
  2022     -6.95%        -13.38%
  2023     -0.71%          9.46%
  2024     11.51%          8.27%
  2025     20.57%         16.33%
  2026     16.51%         11.81%  (to Aug)
```

```
GTAA AGG 3: 2000-08 to 2026-08 (312 months, month-end to month-end)

Strategy (top 3 by momentum, trend filter, rest in cash)
  CAGR                     10.30%
  Max drawdown            -15.59%
  Volatility (annual)      12.16%
  Sharpe (vs T-bills)        0.69
  Best month                9.49%
  Worst month              -8.88%
  Average cash weight        3.3%

Equal-weight (all 13 held at once, 1/13 each, rebalanced monthly)
  CAGR                      7.76%
  Max drawdown            -34.47%
  Volatility (annual)      10.60%
  Sharpe (vs T-bills)        0.55
  Best month                8.41%
  Worst month             -15.72%

Calendar years:
         strategy   equal-weight
  2000     -1.49%         -0.54%  (from Sep)
  2001      4.70%         -0.62%
  2002     18.47%          3.95%
  2003     36.31%         27.50%
  2004     14.98%         15.39%
  2005      8.10%         10.34%
  2006     25.65%         15.76%
  2007     24.62%          9.51%
  2008      9.31%        -20.46%
  2009     10.56%         20.83%
  2010      8.31%         17.04%
  2011      1.59%          3.71%
  2012      2.14%         12.34%
  2013     22.79%          5.82%
  2014      7.78%          5.68%
  2015     -6.75%         -4.48%
  2016      1.80%          9.97%
  2017     18.09%         14.50%
  2018     -4.73%         -6.08%
  2019      4.44%         19.58%
  2020     16.12%         12.01%
  2021     25.50%         11.47%
  2022     -4.35%        -13.38%
  2023     -3.39%          9.46%
  2024      7.56%          8.27%
  2025     23.93%         16.33%
  2026      9.59%         11.81%  (to Aug)
```

### Rolling periods

The full-period CAGR hides how different the experience was depending on
when you started. `gtaa --db extended.duckdb backtest --top 6 --rolling` looks at every 1-,
3- and 5-year window of consecutive months and reports the best and worst
(annualised, with the months they cover), the median, and how many windows
were positive:

```
Rolling returns (annualised, every window of consecutive months):
Strategy
  window       best  (period)               worst  (period)              median  positive
  1 year     39.03%  2020-11 to 2021-10   -10.89%  2015-02 to 2016-01    11.81%   82% of 301
  3 years    21.67%  2003-05 to 2006-04     0.88%  2021-05 to 2024-04     9.77%  100% of 277
  5 years    18.52%  2002-11 to 2007-10     3.21%  2015-04 to 2020-03     9.43%  100% of 253
Equal-weight
  window       best  (period)               worst  (period)              median  positive
  1 year     41.99%  2009-03 to 2010-02   -32.05%  2008-03 to 2009-02     8.67%   82% of 301
  3 years    22.71%  2009-03 to 2012-02    -6.27%  2006-03 to 2009-02     7.06%   97% of 277
  5 years    17.38%  2002-11 to 2007-10     1.05%  2004-03 to 2009-02     6.30%  100% of 253
```

AGG 3 (the equal-weight rows are the same as above):

```
Rolling returns (annualised, every window of consecutive months):
Strategy
  window       best  (period)               worst  (period)              median  positive
  1 year     47.36%  2003-04 to 2004-03   -15.00%  2015-02 to 2016-01    11.08%   78% of 301
  3 years    25.73%  2003-05 to 2006-04    -0.54%  2022-05 to 2025-04     9.27%   99% of 277
  5 years    23.39%  2003-04 to 2008-03     0.47%  2015-02 to 2020-01     8.83%  100% of 253
```

### Underwater

"Underwater" means below a previous high: the months an investor spent
waiting to get back to even. `gtaa --db extended.duckdb backtest --top 6 --underwater` reports
the share of months spent underwater, the longest stretch from a high to
its recovery, the current position, the five deepest drawdowns with how
long each took to reach bottom and then to recover, and the three longest
(the longest is not always among the deepest):

```
Underwater (months spent below the previous equity high):
Strategy
  Time underwater             65% of months
  Longest stretch              32 months (2021-12 to 2024-08)
  Now                      -0.47% below the high
  Deepest drawdowns:
    peak     trough   recovered     depth  to trough  to recover   total
    2008-02  2008-10  2009-09     -12.78%       8 mo       11 mo   19 mo
    2021-12  2023-09  2024-08     -12.33%      21 mo       11 mo   32 mo
    2015-01  2016-01  2017-02     -10.89%      12 mo       13 mo   25 mo
    2018-08  2019-05  2020-08      -9.85%       9 mo       15 mo   24 mo
    2004-03  2004-04  2004-11      -9.75%       1 mo        7 mo    8 mo
  Longest drawdowns (high to recovery):
    peak     trough   recovered     depth  to trough  to recover   total
    2021-12  2023-09  2024-08     -12.33%      21 mo       11 mo   32 mo
    2015-01  2016-01  2017-02     -10.89%      12 mo       13 mo   25 mo
    2018-08  2019-05  2020-08      -9.85%       9 mo       15 mo   24 mo
Equal-weight
  Time underwater             63% of months
  Longest stretch              31 months (2021-12 to 2024-07)
  Now                       0.00% below the high
  Deepest drawdowns:
    peak     trough   recovered     depth  to trough  to recover   total
    2008-05  2009-02  2010-09     -34.47%       9 mo       19 mo   28 mo
    2021-12  2022-09  2024-07     -19.68%       9 mo       22 mo   31 mo
    2019-12  2020-03  2020-07     -14.52%       3 mo        4 mo    7 mo
    2011-04  2011-09  2012-01     -10.41%       5 mo        4 mo    9 mo
    2002-05  2002-09  2003-05      -9.26%       4 mo        8 mo   12 mo
  Longest drawdowns (high to recovery):
    peak     trough   recovered     depth  to trough  to recover   total
    2021-12  2022-09  2024-07     -19.68%       9 mo       22 mo   31 mo
    2008-05  2009-02  2010-09     -34.47%       9 mo       19 mo   28 mo
    2014-08  2016-01  2016-06      -9.02%      17 mo        5 mo   22 mo
```

AGG 3:

```
Underwater (months spent below the previous equity high):
Strategy
  Time underwater             71% of months
  Longest stretch              32 months (2015-01 to 2017-09)
  Now                      -3.97% below the high
  Deepest drawdowns:
    peak     trough   recovered     depth  to trough  to recover   total
    2010-04  2010-08  2011-02     -15.59%       4 mo        6 mo   10 mo
    2022-05  2023-10  2024-11     -15.20%      17 mo       13 mo   30 mo
    2018-08  2019-05  2020-08     -15.06%       9 mo       15 mo   24 mo
    2015-01  2016-01  2017-09     -15.00%      12 mo       20 mo   32 mo
    2008-06  2008-10  2009-09     -13.82%       4 mo       11 mo   15 mo
  Longest drawdowns (high to recovery):
    peak     trough   recovered     depth  to trough  to recover   total
    2015-01  2016-01  2017-09     -15.00%      12 mo       20 mo   32 mo
    2022-05  2023-10  2024-11     -15.20%      17 mo       13 mo   30 mo
    2018-08  2019-05  2020-08     -15.06%       9 mo       15 mo   24 mo
```

What the longer sample adds to the picture from 2014:

- **The difference is made in the two bear markets.** Equal-weight
  lost a third of its value in 2008; AGG 6 was down 1.7% for the year and
  AGG 3 was up. The strategy's worst drawdown over 26 years (−12.8%) is
  smaller than equal-weight's drawdown in 2008 alone.
- **The worst stretches are recent, not in 2008.** The strategy's worst
  1-, 3- and 5-year windows all fall in 2015–2024, inside the ETF period;
  2008 produced its deepest drawdown (12.8%) but it was recovered within
  eleven months. Equal-weight's worst 1-, 3- and 5-year windows all end
  in February 2009: a 32% loss over one year, and a negative 3-year return.
- **The rules lag in strong, broad rallies** (2004–05, 2009–10, 2019, 2023),
  which is the cost of being partly in cash and concentrated in last year's
  leaders. Over the full period that cost was more than repaid, but there
  are multi-year stretches where it was not.
- **AGG 3 is more concentrated, not more defensive.** Its CAGR is almost the
  same as AGG 6's with higher volatility and deeper drawdowns. Its 2008 was
  better because with only three slots it was entirely in commodities, gold
  and one bond fund through the summer, then entirely in Treasuries and cash
  for the crash; AGG 6's fourth to sixth slots were in weaker assets.

The caveats above apply throughout the 2000–2013 portion. By 2008 every
sleeve except momentum was already the ETF (the last switches were BIL in
May 2007 and BWX in October 2007), so that year's result rests on real
funds apart from the S&P 500 standing in for MTUM. The 2000–02 bear market,
on the other hand, is proxies almost throughout, with a mining fund for
gold and a GSCI fund for commodities.
