# Read Me

I want to:
- [X] Get prices from Tibber
- [X] Write the prices and the levels to a dataframe
- [X] Map the price levels to overrides in Nobö. E.g. level VERY_HIGH -> override AWAY
- [X] Create a schedule in Nobö, with the overrides dictated by the price levels
- [X] Send that schedule to the hub
- [ ] Get rid of this warning
  ```
  FutureWarning: The behavior of DataFrame concatenation with empty or all-NA entries is deprecated. In a future version, this will no longer exclude empty or all-NA columns when determining the result dtypes. To retain the old behavior, exclude the relevant entries before the concat operation.
  df_week_profile = pd.concat([top_rows, df_prices_with_mode, bottom_rows], ignore_index=True)
  ```