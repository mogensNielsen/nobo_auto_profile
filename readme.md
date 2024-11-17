# Read Me

I want to:
- [X] Get prices from Tibber
- [X] Write the prices and the levels to a dataframe
- [X] Map the price levels to overrides in Nobö. E.g. level VERY_HIGH -> override AWAY
- [X] Create a schedule in Nobö, with the overrides dictated by the price levels
- [X] Send that schedule to the hub
- [ ] Cleanup old comments
- [ ] Cleanup code in general
- [ ] Consistency in language (e.g. comments in Norwegian should be in English)
- [ ] Get rid of this warning
  ```
  FutureWarning: The behavior of DataFrame concatenation with empty or all-NA entries is deprecated. In a future version, this will no longer exclude empty or all-NA columns when determining the result dtypes. To retain the old behavior, exclude the relevant entries before the concat operation.
  df_week_profile = pd.concat([top_rows, df_prices_with_mode, bottom_rows], ignore_index=True)
  ```
  - [ ] The way the script is now, it overwrites all the days that have been calculated previously. This means that if I run the script on a Wednesday @ 1300, the script will overwrite the profile for the rest of the Wednesday. Is there maybe a way to first get the profile from the hub and then update only tomorrow?