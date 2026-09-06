# Extended backtest, 2000–present

The main backtest starts in 2014 because that is when every ETF in the
universe has a year of history. This directory pushes the start back to
**August 2000** by splicing a mutual fund in front of each ETF, which buys
fourteen more years — two bear markets (2000–02, 2008), a commodity boom,
and a full rate cycle — at the cost of some fidelity.

**Read the results as less reliable than the 2014 ones.** Before each switch
date the strategy is trading a fund that is *similar to* the ETF, not the
ETF, and for three of the fourteen sleeves the substitute is a different
kind of thing altogether (see the notes under the table). The 2014 backtest
answers "what would this portfolio of ETFs have done"; this one answers
"what would the rules have done on the closest tradable funds that existed".

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
   fund was considered and rejected — growth and momentum overlap only some
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

                            strategy  equal-weight
CAGR                          10.23%         7.76%
Max drawdown                 -12.78%       -34.47%
Volatility (annual)            9.76%
Sharpe (vs T-bills)             0.82
Best / worst month             8.17%        -9.75%
Average cash weight             7.6%

Calendar years:
  2000     0.57%   equal-weight   -0.54%  (from Sep)
  2001     2.31%   equal-weight   -0.62%
  2002    12.77%   equal-weight    3.95%
  2003    31.53%   equal-weight   27.50%
  2004    11.78%   equal-weight   15.39%
  2005     6.54%   equal-weight   10.34%
  2006    24.10%   equal-weight   15.76%
  2007    12.65%   equal-weight    9.51%
  2008    -1.73%   equal-weight  -20.46%
  2009    16.85%   equal-weight   20.83%
  2010    13.08%   equal-weight   17.04%
  2011     5.08%   equal-weight    3.71%
  2012     8.79%   equal-weight   12.34%
  2013    23.92%   equal-weight    5.82%
  2014     9.28%   equal-weight    5.68%
  2015    -8.11%   equal-weight   -4.48%
  2016     7.47%   equal-weight    9.97%
  2017    18.84%   equal-weight   14.50%
  2018    -1.72%   equal-weight   -6.08%
  2019     8.03%   equal-weight   19.58%
  2020    11.92%   equal-weight   12.01%
  2021    22.13%   equal-weight   11.47%
  2022    -6.95%   equal-weight  -13.38%
  2023    -0.71%   equal-weight    9.46%
  2024    11.51%   equal-weight    8.27%
  2025    20.57%   equal-weight   16.33%
  2026    16.51%   equal-weight   11.81%  (to Aug)
```

```
GTAA AGG 3: 2000-08 to 2026-08 (312 months, month-end to month-end)

                            strategy  equal-weight
CAGR                          10.30%         7.76%
Max drawdown                 -15.59%       -34.47%
Volatility (annual)           12.16%
Sharpe (vs T-bills)             0.69
Best / worst month             9.49%        -8.88%
Average cash weight             3.3%

Calendar years:
  2000    -1.49%   equal-weight   -0.54%  (from Sep)
  2001     4.70%   equal-weight   -0.62%
  2002    18.47%   equal-weight    3.95%
  2003    36.31%   equal-weight   27.50%
  2004    14.98%   equal-weight   15.39%
  2005     8.10%   equal-weight   10.34%
  2006    25.65%   equal-weight   15.76%
  2007    24.62%   equal-weight    9.51%
  2008     9.31%   equal-weight  -20.46%
  2009    10.56%   equal-weight   20.83%
  2010     8.31%   equal-weight   17.04%
  2011     1.59%   equal-weight    3.71%
  2012     2.14%   equal-weight   12.34%
  2013    22.79%   equal-weight    5.82%
  2014     7.78%   equal-weight    5.68%
  2015    -6.75%   equal-weight   -4.48%
  2016     1.80%   equal-weight    9.97%
  2017    18.09%   equal-weight   14.50%
  2018    -4.73%   equal-weight   -6.08%
  2019     4.44%   equal-weight   19.58%
  2020    16.12%   equal-weight   12.01%
  2021    25.50%   equal-weight   11.47%
  2022    -4.35%   equal-weight  -13.38%
  2023    -3.39%   equal-weight    9.46%
  2024     7.56%   equal-weight    8.27%
  2025    23.93%   equal-weight   16.33%
  2026     9.59%   equal-weight   11.81%  (to Aug)
```

What the longer sample adds to the picture from 2014:

- **The two bear markets are where the rules earn their keep.** Equal-weight
  lost a third of its value in 2008; AGG 6 was down 1.7% for the year and
  AGG 3 was up. The strategy's worst drawdown over 26 years (−12.8%) is
  smaller than equal-weight's drawdown in 2008 alone.
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
