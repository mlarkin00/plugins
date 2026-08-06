# Pitfall

* [ls does not honour argument order](ls-argument-order.md) - ls sorts its arguments, so `ls a b c | head -1` returns the alphabetically smallest path, which can silently select a stale cached copy.
* [Popping a patched module makes tests hit the network](patched-module-reload.md) - sys.modules.pop() inside a test body discards the @patch-ed module, so the fresh import rebinds the real function and assertFalse(mock.called) passes vacuously.
* [rsync --delete does not delete excluded files](rsync-protects-excluded.md) - rsync exclude rules are two-sided, so an anchored `- /*` both filters the transfer and protects matching destination entries from --delete, letting a mirror silently grow into a superset of its source.
