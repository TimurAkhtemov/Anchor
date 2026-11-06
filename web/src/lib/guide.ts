// The "How to read this" text, carried over from the Streamlit Quick Guide and
// the macro cards' help tooltips (app/app.py). Words are unchanged; only the
// markdown is dropped, the intro's trailing colon becomes a period, and the
// "Regime Chips" heading names what this page shows.

export const GUIDE_INTRO =
  "This section shows the macro economic regime of the U.S. economy. Understanding this is crucial because it sets the backdrop for stock market behavior.";

export const GUIDE_INDICATORS: { name: string; text: string }[] = [
  {
    name: "Fed Funds Rate & 10-Year Treasury",
    text: "Benchmark interest rates. Rising rates increase borrowing costs for consumers and businesses, slowing down spending and stock market valuations.",
  },
  {
    name: "Inflation (YoY)",
    text: "Shows how fast prices are rising. High inflation forces the Fed to raise interest rates to cool the economy.",
  },
  {
    name: "Unemployment Rate",
    text: "Reflects the strength of the jobs market. A very strong labor market supports consumer spending but can lead to inflation pressure.",
  },
];

export const GUIDE_REGIME_STATES: {
  name: string;
  states: { state: string; rule: string }[];
}[] = [
  {
    name: "Rates",
    states: [
      {
        state: "rising",
        rule: "Fed Funds Rate increased by 0.25 pp or more over 3 months (at least one standard Fed rate hike).",
      },
      {
        state: "easing",
        rule: "Fed Funds Rate decreased by 0.25 pp or more over 3 months (at least one standard Fed rate cut).",
      },
      {
        state: "steady",
        rule: "Changed by less than 0.25 pp (rates are flat/unchanged).",
      },
    ],
  },
  {
    name: "Inflation",
    states: [
      {
        state: "rising",
        rule: "YoY Inflation increased by 0.30 pp or more over 3 months (inflation heating up).",
      },
      {
        state: "cooling",
        rule: "YoY Inflation decreased by 0.30 pp or more over 3 months (inflation cooling down).",
      },
      {
        state: "stable",
        rule: "Changed by less than 0.30 pp (prices are steady).",
      },
    ],
  },
  {
    name: "Labor",
    states: [
      {
        state: "loosening",
        rule: "Unemployment Rate increased by 0.20 pp or more over 3 months (more job seekers, hiring cooling).",
      },
      {
        state: "tightening",
        rule: "Unemployment Rate decreased by 0.20 pp or more over 3 months (fewer job seekers, job market heating).",
      },
      {
        state: "stable",
        rule: "Changed by less than 0.20 pp (labor market is steady).",
      },
    ],
  },
];

// Keys match macro_indicators.indicator_key; order is the macro column order.
export const MACRO_CARDS: { key: string; label: string; help: string }[] = [
  {
    key: "fed_funds_rate",
    label: "Fed funds rate",
    help: "The benchmark interest rate set by the Federal Reserve. When it rises, bank lending costs increase, driving up rates on mortgages, credit cards, and business loans to cool down spending.",
  },
  {
    key: "ten_year_yield",
    label: "10-year Treasury",
    help: "The interest rate paid on 10-year U.S. government debt. It serves as a benchmark for long-term lending rates and heavily influences how stock market valuations (especially tech) are discounted.",
  },
  {
    key: "inflation_yoy",
    label: "Inflation (YoY)",
    help: "The year-over-year rate at which consumer prices are rising (based on the Consumer Price Index). High inflation shrinks consumer purchasing power.",
  },
  {
    key: "unemployment_rate",
    label: "Unemployment",
    help: "The percentage of the labor force actively seeking work. Low unemployment signals a healthy consumer economy but can contribute to wage inflation.",
  },
];
