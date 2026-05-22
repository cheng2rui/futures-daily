# DCE fallback notes

AkShare 1.18.55 currently fails on DCE official daily/seat endpoints in this environment:

- `get_dce_daily(date=...)` → `JSONDecodeError`
- `get_dce_rank_table(date=...)` → empty `{}` on recent dates
- `futures_dce_position_rank(date=...)` → `BadZipFile`

## Implemented fallback

`app/sources/dce_fallback_source.py` provides a **daily行情 fallback** using Sina futures continuous contracts:

- Uses `ak.futures_display_main_sina()` when available to discover active DCE continuous symbols.
- Falls back to a curated DCE variety list.
- Fetches `ak.futures_zh_daily_sina(symbol=...)` per variety.
- Emits normalized rows compatible with the normal collector.

Known limitations:

- This is continuous/main-contract style data, not the full exchange daily table.
- Turnover and previous settlement may be missing.
- Contract code is approximated when Sina does not expose exact contract metadata.
- The collector records the source warning so the data quality panel can show partial/fallback coverage.

## Seat rank fallback

No reliable public fallback was found for DCE member/seat rank.

The adapter intentionally returns a clear error instead of fabricating partial data. Later options:

1. Monitor DCE official site / AkShare fixes.
2. Implement a dedicated official-site parser if the new endpoint format is identified.
3. Use commercial data such as Tushare Pro or another futures data provider.
