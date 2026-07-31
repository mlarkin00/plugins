# Pitfall

* [An agent whose frontmatter is not valid YAML is skipped silently](agent-frontmatter-yaml.md) - Claude Code drops a malformed agent definition with no error — it is simply absent from the dispatch list. A `description` carrying `<example>` blocks must be a block scalar, and only a real YAML parse detects the failure.
* [Updating an installed Claude Code plugin](plugin-updates.md) - claude plugin update needs the name@marketplace form, and `details` resolves the newest cached version rather than the loaded one — so a fix can look live while the session still runs old code.

# Runtime Behaviour

* [Injected context is stored as typed records, not as rendered system-reminder text](transcript-injected-context.md) - The transcript keeps structured attachment records; the <system-reminder> wrapping is applied at send time and never written, so grepping for it returns zero hits in a session full of injections.
