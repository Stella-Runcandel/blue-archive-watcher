## Testing

### Run all tests
```bash
python -m unittest discover -s tests
```

### Coverage overview
* **Storage tests** cover SQLite profile/frame/reference metadata, filesystem migration, and debug eviction.
* **FFmpeg parsing tests** validate DirectShow device list parsing without invoking FFmpeg.
* **Pipeline tests** validate bounded queue drop behavior.
* **Detection tests** validate deterministic outputs on fixed inputs.
* **Profile switching tests** validate monitoring state preservation.
* **Status monitor tests** validate dashboard metrics label updates headlessly (Qt offscreen).

### Mocking strategy
* FFmpeg is not invoked; parsing is tested with static sample output.
* SQLite and filesystem are isolated using temporary directories and `APP_DB_PATH`.
* Qt UI tests use `QT_QPA_PLATFORM=offscreen`.
