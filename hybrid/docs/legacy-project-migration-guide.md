# Legacy project migration guide

1. Keep the previous InkOS and Runtime packages plus a verified project backup.
2. Migrate old configuration explicitly:

   ```powershell
   cd inkos
   pnpm migrate:phase8-config -- C:\path\to\project
   ```

   Review the warnings and keep `inkos.json.pre-phase8.bak` until acceptance is complete.

3. Open the legacy project read-only. Confirm chapter export and backup creation.
4. In Studio Migration Manager, create a job, scan, resolve every blocking conflict, run dry-run, and create a verified snapshot.
5. Import and verify chapter checksum coverage, doctor, replay/projection hash, provenance and export.
6. Confirm cutover explicitly. Re-run Studio, CLI status, doctor and a chapter query.
7. If rollback is required, stop applications and restore the verified pre-migration snapshot with the previous stable packages. Do not enable dual-write.

Markdown edits made before or after migration never auto-bootstrap authority. To change canon after cutover, use a typed Studio edit or Runtime command with the expected revision.
