# Security Policy / Политика безопасности

## Supported versions

Only the latest release on the `main` branch is supported. The project is at an early stage (0.1.x).

## Reporting a vulnerability

Please **do not** open a public issue with exploit details.

Use GitHub's private reporting: open the **Security** tab of this repository and choose
**Report a vulnerability**. If that option is not available, open a public issue that says only that you have a
security problem (no technical details), and the maintainer will arrange a private channel.

Пожалуйста, **не** публикуйте детали уязвимости в открытом issue. Воспользуйтесь вкладкой **Security → Report a
vulnerability**. Если её нет, создайте issue только с фразой о том, что у вас есть проблема безопасности (без
технических подробностей), и мы договоримся о закрытом канале.

## What counts as a vulnerability here

CodeCheck MCP opens web pages in a browser and reads project folders on behalf of an AI agent, so these are in scope:

- Escaping the "read-only" guarantee: the server modifying the project under test.
- Navigation or data leaving to external domains despite the block.
- Secrets appearing unmasked in reports or tool output.
- Reading files outside the project folder given as `target`.
- Unsafe handling of untrusted pages (a hostile site tricking the server into harmful actions).

Findings that the tool reports about *your* project (for example, a false negative in a check) are ordinary bugs,
not vulnerabilities: please use a normal issue.

## Responsible use

Point the server only at projects you own or are allowed to test.
